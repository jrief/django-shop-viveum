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
from django.core.exceptions import SuspiciousOperation
from django.shortcuts import render_to_response
from django.contrib.auth.models import AnonymousUser
from django.template import RequestContext
from django.http import HttpResponse, HttpResponseRedirect, \
    HttpResponseBadRequest, HttpResponseServerError
from django.views.decorators.csrf import csrf_exempt
from shop.util.address import get_billing_address_from_request
from forms import OrderStandardForm
from models import Confirmation


class OffsiteViveumBackend(object):
    '''
    Glue code to let django-SHOP talk to the Viveum backend.
    '''
    backend_name = url_namespace = 'viveum'
    SHA_IN_PARAMETERS = ('AMOUNT', 'BRAND', 'CURRENCY', 'CN', 'EMAIL', 'LANGUAGE',
        'ORDERID', 'PSPID', 'TITLE', 'PM', 'OWNERZIP', 'OWNERADDRESS', 'OWNERADDRESS2',
        'OWNERTOWN', 'OWNERCTY',)

    #===========================================================================
    # Defined by the backends API
    #===========================================================================

    def __init__(self, shop):
        self.shop = shop
        self.logger = logging.getLogger(__name__)
        self.SHA_IN_PARAMETERS = set(self.SHA_IN_PARAMETERS)
        assert type(settings.VIVEUM_PAYMENT).__name__ == 'dict', \
            "You need to configure a VIVEUM_PAYMENT dictionary in settings"

    def get_urls(self):
        urlpatterns = patterns('',
            url(r'^$', self.view_that_asks_for_money, name='viveum'),
            url(r'^success$', self.viveum_return_success_view, name='viveum_success'),
            url(r'^error$', self.view_that_asks_for_money, name='viveum_error'),
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
        url_scheme = 'https' if request.is_secure() else 'http'
        url_domain = get_current_site(request).domain
        form_dict = {
            'PSPID': settings.VIVEUM_PAYMENT.get('PSPID'),
            'CURRENCY': settings.VIVEUM_PAYMENT.get('CURRENCY'),
            'LANGUAGE': settings.VIVEUM_PAYMENT.get('LANGUAGE'),
            'TITLE': settings.VIVEUM_PAYMENT.get('TITLE'),
            'ORDERID': order.id,
            'AMOUNT': int(self.shop.get_order_total(order) * 100),
            'CN': getattr(billing_address, 'name', ''),
            'EMAIL': email,
            'OWNERZIP': getattr(billing_address, 'zip_code', ''),
            'OWNERADDRESS': getattr(billing_address, 'address', ''),
            'OWNERADDRESS2': getattr(billing_address, 'address2', ''),
            'OWNERTOWN': getattr(billing_address, 'city', ''),
            'OWNERCTY': getattr(billing_address, 'country', ''),
        }
        form_dict.update({ 'SHASIGN': self._get_shasign(form_dict) })
        return form_dict

    def _get_shasign(self, form_dict):
        """
        Add the cryptographic SHA1 signature to the given form dictionary.
        """
        sha_in_parameters = sorted(self.SHA_IN_PARAMETERS.intersection(form_dict.iterkeys()))
        sha_in_parameters = filter(lambda key: form_dict.get(key), sha_in_parameters)
        print sha_in_parameters
        passphrase = settings.VIVEUM_PAYMENT.get('PASSPHRASE')
        values = ['%s=%s%s' % (key.upper(), form_dict.get(key), passphrase) for key in sha_in_parameters]
        #print ''.join(values)
        return hashlib.sha1(''.join(values)).hexdigest().upper()

    def get_processor_urls(self, request):
            url = 'https://' if request.is_secure() else 'http://'
            url += get_current_site(request).domain
            self.logger.debug('Processor URL: %s' % url)
            return {
                'redirectUrl': url + reverse('ipayment_success'),
                'silentErrorUrl': url + reverse('ipayment_error'),
                'hiddenTriggerUrl': url + reverse('ipayment_hidden'),
            }

    #===========================================================================
    # Handlers, which process GET redirects initiated by IPayment
    #===========================================================================

    def viveum_return_success_view(self, request):
        """
        The view the customer is redirected to from the IPayment server after a
        successful payment.
        This view is called after 'payment_was_successful' has been called, so
        the confirmation of the payment is always available here.
        """
        if request.method != 'GET':
            return HttpResponseBadRequest('Request method %s not allowed here' %
                                          request.method)
        try:
            shopper_id = int(request.GET['shopper_id'])
            self.logger.info('IPayment for order %s redirected client with status %s',
                             shopper_id, request.GET['ret_status'])
            if request.GET['ret_status'] != 'SUCCESS':
                return HttpResponseRedirect(self.shop.get_cancel_url())
            confirmation = Confirmation.objects.filter(shopper_id=shopper_id)
            if confirmation.count() == 0:
                raise SuspiciousOperation('Redirect by IPayment rejected: '
                    'No order confirmation found for shopper_id %s.' % shopper_id)
            return HttpResponseRedirect(self.shop.get_finished_url())
        except Exception as exception:
            # since this response is sent to IPayment, catch errors locally
            logging.error(exception.__str__())
            traceback.print_exc()
            return HttpResponseServerError('Internal error in ' + __name__)

    #===========================================================================
    # Handlers, which process POST data from IPayment
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
            if settings.IPAYMENT['checkOriginatingIP']:
                self._check_originating_ipaddr(request)
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

    def _check_originating_ipaddr(self, request):
        """
        Check that the request is coming from a trusted source. A list of
        allowed sources is hard coded into this module.
        If the software is operated behind a proxy, instead of using the remote
        IP address, the HTTP-header HTTP_X_FORWARDED_FOR is evaluated against
        the list of allowed sources.
        """
        # TODO: use request.get_host()
        originating_ip = request.META['REMOTE_ADDR']
        if settings.IPAYMENT['reverseProxies'].count(originating_ip):
            if 'HTTP_X_FORWARDED_FOR' in request.META:
                forged = True
                for client in request.META['HTTP_X_FORWARDED_FOR'].split(','):
                    if self.ALLOWED_CONFIRMERS.count(client):
                        forged = False
                        originating_ip = client
                        break
                if forged:
                    raise SuspiciousOperation('Request invoked from suspicious IP address %s'
                                    % request.META['HTTP_X_FORWARDED_FOR'])
            else:
                logging.warning('Allowed proxy servers are declared, but header HTTP_X_FORWARDED_FOR is missing')
        elif not self.ALLOWED_CONFIRMERS.count(originating_ip):
            raise SuspiciousOperation('Request invoked from suspicious IP address %s'
                                      % originating_ip)
        self.logger.debug('POST data received from IPayment[%s]: %s.'
                          % (originating_ip, request.POST.__str__()))
