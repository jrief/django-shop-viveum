#-*- coding: utf-8 -*-
from datetime import datetime
from decimal import Decimal
import hashlib
import logging
import traceback
from django.conf import settings
from django.conf.urls.defaults import patterns, url
from django.contrib.sites.models import get_current_site
from django.core.urlresolvers import reverse
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.shortcuts import render_to_response
from django.contrib.auth.models import AnonymousUser
from django.views.generic import TemplateView
from django.template import RequestContext
from django.http import HttpResponse, HttpResponseRedirect, \
    HttpResponseBadRequest, HttpResponseServerError
from django.views.decorators.csrf import csrf_exempt
from shop.util.address import get_billing_address_from_request
from forms import OrderStandardForm, ConfirmationForm
from models import Confirmation


class OffsiteViveumBackend(object):
    '''
    Glue code to let django-SHOP talk to the Viveum backend.
    '''
    backend_name = url_namespace = 'viveum'
    SHA_IN_PARAMETERS = set(('AMOUNT', 'BRAND', 'CURRENCY', 'CN', 'EMAIL', 'TP',
        'LANGUAGE', 'ORDERID', 'PSPID', 'TITLE', 'PM', 'OWNERZIP', 'OWNERADDRESS',
        'OWNERADDRESS2', 'OWNERTOWN', 'OWNERCTY', 'ACCEPTURL', 'DECLINEURL',
        'EXCEPTIONURL', 'CANCELURL', 'COM'))
    SHA_OUT_PARAMETERS = set(('ACCEPTANCE', 'AMOUNT', 'CARDNO', 'CN', 'CURRENCY',
         'IP', 'NCERROR', 'ORDERID', 'PAYID', 'STATUS', 'BRAND'))
    CONFIRMATION_PARAMETERS = [f.name for f in Confirmation.get_meta_fields()]

    #===========================================================================
    # Defined by the backends API
    #===========================================================================

    def __init__(self, shop):
        self.shop = shop
        self.logger = logging.getLogger(__name__)
        assert type(settings.VIVEUM_PAYMENT).__name__ == 'dict', \
            "You need to configure a VIVEUM_PAYMENT dictionary in settings"

    def get_urls(self):
        urlpatterns = patterns('',
            url(r'^$', self.view_that_asks_for_money, name='viveum'),
            url(r'^template.html$', TemplateView.as_view(template_name='payment_zone.html'), name='viveum_template'),
            url(r'^accept$', self.return_success_view, {'origin': 'acquirer'}, name='viveum_accept'),
            url(r'^decline$', self.return_decline_view, {'origin': 'acquirer'}, name='viveum_decline'),
            url(r'^viveum-confirm$', self.return_success_view, {'origin': 'acquirer'}, name='viveum_confirm'),
            url(r'^viveum-cancel$', self.return_decline_view, {'origin': 'acquirer'}, name='viveum_cancel'),
        )
        return urlpatterns

    #===========================================================================
    # Views
    #===========================================================================

    def view_that_asks_for_money(self, request):
        """
        Show this form to ask the customer to proceed for payment at Viveum.
        """
        form = OrderStandardForm(initial=self._get_form_dict(request))
        context = {"form": form}
        rc = RequestContext(request, context)
        return render_to_response('payment.html', rc)

    def _get_form_dict(self, request):
        """
        From the current order, create a dictionary to initialize a hidden form.
        """
        order = self.shop.get_order(request)
        billing_address = get_billing_address_from_request(request)
        email = ''
        if request.user and not isinstance(request.user, AnonymousUser):
            email = request.user.email
        url_scheme = 'https://%s%s' if request.is_secure() else 'http://%s%s'
        domain = get_current_site(request).domain
        form_dict = {
            'PSPID': settings.VIVEUM_PAYMENT.get('PSPID'),
            'CURRENCY': settings.VIVEUM_PAYMENT.get('CURRENCY'),
            'LANGUAGE': settings.VIVEUM_PAYMENT.get('LANGUAGE'),
            'TITLE': settings.VIVEUM_PAYMENT.get('TITLE'),
            'ORDERID': order.id,
            'AMOUNT': int(self.shop.get_order_total(order) * 100),
            'CN': getattr(billing_address, 'name', ''),
            'COM': settings.VIVEUM_PAYMENT.get('ORDER_DESCRIPTION', '') % order.id,
            'EMAIL': email,
            'TP': url_scheme % (domain, reverse('viveum_template')),
            'OWNERZIP': getattr(billing_address, 'zip_code', ''),
            'OWNERADDRESS': getattr(billing_address, 'address', ''),
            'OWNERADDRESS2': getattr(billing_address, 'address2', ''),
            'OWNERTOWN': getattr(billing_address, 'city', ''),
            'OWNERCTY': getattr(billing_address, 'country', ''),
            'ACCEPTURL': url_scheme % (domain, reverse('viveum_accept')),
            'DECLINEURL': url_scheme % (domain, reverse('viveum_decline')),
        }
        form_dict['SHASIGN'] = self._get_sha_sign(form_dict, self.SHA_IN_PARAMETERS,
                                settings.VIVEUM_PAYMENT.get('SHA1_IN_SIGNATURE'))
        return form_dict

    def _get_sha_sign(self, form_dict, parameters, passphrase):
        """
        Add the cryptographic SHA1 signature to the given form dictionary.
        """
        form_dict = dict((key.upper(), value) for key, value in form_dict.iteritems())
        sha_parameters = sorted(parameters.intersection(form_dict.iterkeys()))
        sha_parameters = filter(lambda key: form_dict.get(key), sha_parameters)
        values = ['%s=%s%s' % (key.upper(), form_dict.get(key), passphrase) for key in sha_parameters]
        return hashlib.sha1(''.join(values)).hexdigest().upper()

    def _receive_confirmation(self, request, origin):
        query_dict = dict((key.lower(), value) for key, value in request.GET.iteritems())
        query_dict.update({
            'order': query_dict.get('orderid', 0),
            'origin': origin,
        })
        confirmation = ConfirmationForm(query_dict)
        if confirmation.is_valid():
            confirmation.save()
        else:
            raise ValidationError('Confirmation sent by PSP did not validate: %s' % confirmation.errors)
        shaoutsign = self._get_sha_sign(query_dict, self.SHA_OUT_PARAMETERS,
                        settings.VIVEUM_PAYMENT.get('SHA1_OUT_SIGNATURE'))
        if shaoutsign != confirmation.cleaned_data['shasign']:
            raise SuspiciousOperation('Confirm redirection by PSP has a divergent SHA1 signature')
        self.logger.info('PSP redirected client with status %s for order %s',
            confirmation.cleaned_data['status'], confirmation.cleaned_data['orderid'])
        return confirmation

    #===========================================================================
    # Handlers, which process GET redirects initiated by IPayment
    #===========================================================================

    def return_success_view(self, request, origin):
        """
        The view the customer is redirected to from the PSP after he performed
        a successful payment.
        """
        if request.method != 'GET':
            return HttpResponseBadRequest('Request method %s not allowed here' %
                                          request.method)
        try:
            confirmation = self._receive_confirmation(request, origin)
            if not str(confirmation.cleaned_data['status']).startswith('5'):
                return HttpResponseRedirect(self.shop.get_cancel_url())
            self.shop.confirm_payment(confirmation.cleaned_data['order'],
                confirmation.cleaned_data['amount'],
                confirmation.cleaned_data['payid'], self.backend_name)
            return HttpResponseRedirect(self.shop.get_finished_url())
        except Exception as exception:
            # since this response is sent back to the PSP, catch errors locally
            logging.error('%s while performing request %s' % (exception.__str__(), request))
            traceback.print_exc()
            return HttpResponseServerError('Internal error in ' + __name__)

    def return_decline_view(self, request, origin):
        """
        The view the customer is redirected to from the IPayment server after a
        successful payment.
        This view is called after 'payment_was_successful' has been called, so
        the confirmation of the payment is always available here.
        """
        # orderID=867515&currency=EUR&amount=1%2E23&ACCEPTANCE=&STATUS=1&CARDNO=XXXXXXXXXXXX3333&CN=John+Doe&PAYID=17186499&NCERROR=30001001&BRAND=VISA&IP=194%2E166%2E162%2E210&SHASIGN=7C73D6A079E2BFD3B903E42FDE2D9DD52453526C
        if request.method != 'GET':
            return HttpResponseBadRequest('Request method %s not allowed here' %
                                          request.method)
        try:
            self._receive_confirmation(request, origin)
            return HttpResponseRedirect(self.shop.get_cancel_url())
        except Exception as exception:
            # since this response is sent back to the PSP, catch errors locally
            logging.error('%s while performing request %s' % (exception.__str__(), request))
            traceback.print_exc()
            return HttpResponseServerError('Internal error in ' + __name__)

    #===========================================================================
    # Handlers, which process the confirmation request sent by the PSP
    #===========================================================================

    @csrf_exempt
    def payment_was_successful(self, request):
        '''
        This listens to a confirmation sent by one of the IPayment servers.
        Valid payments are commited as confirmed payments into their model.
        The intention of this view is not to display any useful information,
        since the HTTP-client is a server located at IPayment.
        '''
        if request.method != 'POST':
            return HttpResponseBadRequest()
        try:
            post = request.POST.copy()
            if 'trx_amount' in post:
                post['trx_amount'] = (Decimal(post['trx_amount']) / Decimal('100')) \
                                                    .quantize(Decimal('0.00'))
            if 'ret_transdate' and 'ret_transtime' in post:
                post['ret_transdatetime'] = datetime.strptime(
                    post['ret_transdate'] + ' ' + post['ret_transtime'],
                    '%d.%m.%y %H:%M:%S')
            confirmation = ConfirmationForm(post)
            if not confirmation.is_valid():
                raise SuspiciousOperation('Confirmation by IPayment rejected: '
                            'POST data does not contain all expected fields.')
            if not settings.IPAYMENT['useSessionId']:
                self._check_ret_param_hash(request.POST)
            confirmation.save()
            order = self.shop.get_order_for_id(confirmation.cleaned_data['shopper_id'])
            self.logger.info('IPayment for %s confirmed %s', order,
                             confirmation.cleaned_data['ret_status'])
            if confirmation.cleaned_data['ret_status'] == 'SUCCESS':
                self.shop.confirm_payment(order, confirmation.cleaned_data['trx_amount'],
                    confirmation.cleaned_data['ret_trx_number'], self.backend_name)
            return HttpResponse('OK')
        except Exception as exception:
            # since this response is sent to IPayment, catch errors locally
            logging.error('POST data: ' + request.POST.__str__())
            logging.error(exception.__str__())
            traceback.print_exc()
            return HttpResponseServerError('Internal error in ' + __name__)
