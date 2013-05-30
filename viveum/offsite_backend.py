#-*- coding: utf-8 -*-
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
from django.template import RequestContext
from django.http import HttpResponseRedirect, HttpResponseBadRequest, HttpResponseServerError
from shop.util.address import get_billing_address_from_request
from forms import OrderStandardForm, ConfirmationForm
from models import Confirmation
from views import PaymentZoneView


class OffsiteViveumBackend(object):
    """
    Glue code to let django-SHOP talk to the Viveum PSP.
    """
    backend_name = url_namespace = 'viveum'
    SHA_IN_PARAMETERS = set(('AMOUNT', 'BRAND', 'CURRENCY', 'CN', 'EMAIL', 'TP',
        'LANGUAGE', 'ORDERID', 'PSPID', 'TITLE', 'PM', 'OWNERZIP', 'OWNERADDRESS',
        'OWNERADDRESS2', 'OWNERTOWN', 'OWNERCTY', 'ACCEPTURL', 'DECLINEURL',
        'EXCEPTIONURL', 'CANCELURL', 'COM'))
    SHA_OUT_PARAMETERS = set(('ACCEPTANCE', 'AMOUNT', 'CARDNO', 'CN', 'CURRENCY',
         'IP', 'NCERROR', 'ORDERID', 'PAYID', 'STATUS', 'BRAND'))
    CONFIRMATION_PARAMETERS = [f.name for f in Confirmation.get_meta_fields()]

    def __init__(self, shop):
        self.shop = shop
        self.logger = logging.getLogger(__name__)
        assert type(settings.VIVEUM_PAYMENT).__name__ == 'dict', \
            "You must configure the VIVEUM_PAYMENT dictionary in your settings"

    def get_urls(self):
        urlpatterns = patterns('',
            url(r'^$', self.proceed_payment_view, name='viveum'),
            url(r'^template.html$', PaymentZoneView.as_view(), name='viveum_template'),
            url(r'^accept$', self.return_success_view, {'origin': 'acquirer'}, name='viveum_accept'),
            url(r'^decline$', self.return_decline_view, {'origin': 'acquirer'}, name='viveum_decline'),
        )
        return urlpatterns

    def proceed_payment_view(self, request):
        """
        Show this form to the customer. It will be proceeded to PSP Viveum using
        method POST.
        """
        form_dict = self.get_form_dict(request)
        self.sign_form_dict(form_dict)
        order_form = OrderStandardForm(initial=form_dict)
        request_context = RequestContext(request, {'order_form': order_form})
        return render_to_response('viveum/order_form.html', request_context)

    def get_form_dict(self, request):
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
        return {
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

    def sign_form_dict(self, form_dict):
        form_dict['SHASIGN'] = self._get_sha_sign(form_dict,
            self.SHA_IN_PARAMETERS,
            settings.VIVEUM_PAYMENT.get('SHA1_IN_SIGNATURE'))

    def _get_sha_sign(self, form_dict, parameters, passphrase):
        """
        Add the cryptographic SHA1 signature to the given form dictionary.
        """
        form_dict = dict((key.upper(), value) for key, value in form_dict.iteritems())
        sha_parameters = sorted(parameters.intersection(form_dict.iterkeys()))
        sha_parameters = filter(lambda key: form_dict.get(key), sha_parameters)
        values = [('%s=%s%s' % (key.upper(), form_dict.get(key), passphrase)).encode('utf8') for key in sha_parameters]
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
        The view the customer is redirected to from the PSP after the payment
        was successful.
        """
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
