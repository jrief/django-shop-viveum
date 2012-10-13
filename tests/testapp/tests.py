# -*- coding: utf-8 -*-
import httplib
import httplib2
import urllib
import urlparse
from pyquery.pyquery import PyQuery
#from lxml import etree
import random
from decimal import Decimal
from django.contrib.sites.models import Site
from django.test import LiveServerTestCase
from django.test.client import Client, RequestFactory
from django.conf import settings
from django.core.urlresolvers import reverse, resolve
from django.contrib.auth.models import User
from shop.util.cart import get_or_create_cart
from shop.addressmodel.models import Country
from shop.models.ordermodel import Order
from shop.backends_pool import backends_pool
from shop.tests.util import Mock
from viveum.models import Confirmation
from testapp.models import DiaryProduct


class ViveumTest(LiveServerTestCase):
    def setUp(self):
        self.save_received_data = settings.DEBUG  # leave a hard copy of the html sources received from the PSP
        current_site = Site.objects.get(id=settings.SITE_ID)
        current_site.domain = settings.HOST_NAME
        current_site.save()
        self._create_fake_order()
        self.viveum_backend = backends_pool.get_payment_backends_list()[0]
        self.factory = RequestFactory()
        self.request = Mock()
        setattr(self.request, 'session', {})
        setattr(self.request, 'is_secure', lambda: False)
        user = User.objects.create(username="test", email="test@example.com",
            first_name="Test", last_name="Tester",
            password="sha1$fc341$59561b971056b176e8ebf0b456d5eac47b49472b")
        setattr(self.request, 'user', user)
        self.country_usa = Country(name='USA')
        self.country_usa.save()
        self.client = Client()
        self.client.login(username='test', password='123')
        self._create_cart()
        self._go_shopping()

    def tearDown(self):
        pass

    def _create_cart(self):
        self.product = DiaryProduct(isbn='1234567890', number_of_pages=100)
        self.product.name = 'test'
        self.product.slug = 'test'
        self.product.short_description = 'test'
        self.product.long_description = 'test'
        self.product.unit_price = Decimal('1.23')
        self.product.save()
        self.cart = get_or_create_cart(self.request, True)
        self.cart.add_product(self.product, 1)
        self.cart.save()

    def _go_shopping(self):
        # add address information
        post = {
            'ship-name': 'John Doe',
            'ship-address': 'Rosestreet',
            'ship-address2': '',
            'ship-zip_code': '01234',
            'ship-city': 'Toledeo',
            'ship-state': 'Ohio',
            'ship-country': self.country_usa.pk,
            'bill-name': 'John Doe',
            'bill-address': 'Rosestreet',
            'bill-address2': '',
            'bill-zip_code': '01234',
            'bill-city': 'Toledeo',
            'bill-state': 'Ohio',
            'bill-country': self.country_usa.pk,
            'shipping_method': 'flat',
            'payment_method': 'viveum',
        }
        response = self.client.post(reverse('checkout_selection'), post, follow=True)
        urlobj = urlparse.urlparse(response.redirect_chain[0][0])
        self.assertEqual(resolve(urlobj.path).url_name, 'checkout_shipping')
        urlobj = urlparse.urlparse(response.redirect_chain[1][0])
        self.assertEqual(resolve(urlobj.path).url_name, 'flat')
        self.order = self.viveum_backend.shop.get_order(self.request)

    def _simulate_payment(self):
        """
        Simulate a payment to Viveum's payment processor.
        The full payment information is sent with method POST.
        """
        post = self.viveum_backend.get_hidden_context(self.order)
        post['advanced_strict_id_check'] = 0  # disabled for testing only
        # (see ipayment_Technik-Handbuch.pdf page 32)
        if settings.IPAYMENT['useSessionId']:
            post['ipayment_session_id'] = self.viveum_backend.get_session_id(self.request, self.order)
        else:
            post.update(self.viveum_backend.get_sessionless_context(self.request, self.order))
            post['trx_securityhash'] = self.viveum_backend._calc_trx_security_hash(post)
        post.update({
            'addr_name': 'John Doe',
            'cc_number': '4012888888881881',  # Visa test credit card number
            'cc_checkcode': '123',
            'cc_expdate_month': '12',
            'cc_expdate_year': '2029',
        })
        ipayment_uri = '/merchant/%s/processor/2.0/' % settings.IPAYMENT['accountId']
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "Accept": "text/plain"
        }
        conn = httplib.HTTPSConnection('ipayment.de')
        conn.request("POST", ipayment_uri, urllib.urlencode(post), headers)
        httpresp = conn.getresponse()
        self.assertEqual(httpresp.status, 302, 'Expected to be redirected back from IPayment')
        redir_url = urlparse.urlparse(httpresp.getheader('location'))
        query_params = urlparse.parse_qs(redir_url.query)
        redir_uri = redir_url.path + '?' + redir_url.query
        conn.close()
        self.assertEqual(query_params['ret_status'][0], 'SUCCESS', 'IPayment reported: ' + redir_uri)

        # IPayent redirected the customer onto 'redir_uri'. Continue to complete the order.
        response = self.client.get(redir_uri, follow=True)
        self.assertEqual(len(response.redirect_chain), 1, '')
        urlobj = urlparse.urlparse(response.redirect_chain[0][0])
        self.assertEqual(resolve(urlobj.path).url_name, 'thank_you_for_your_order')
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(pk=self.order.id)
        self.assertEqual(order.status, Order.COMPLETED)
        confirmation = Confirmation.objects.get(shopper_id=self.order.id)
        self.assertEqual(confirmation.ret_status, 'SUCCESS')

    def _create_fake_order(self):
        """
        Create a fake order with a random order id, so that the following real
        order does not start with 1. Otherwise this could cause errors if this
        test is invoked multiple times.
        """
        order_id = random.randint(100001, 999999)
        Order.objects.create(id=order_id, status=Order.CANCELLED)

    def _send_transaction_data(self):
        """
        Send data fields for the current transaction to our PSP using method POST.
        """
        form_dict = self.viveum_backend._get_form_dict(self.request)
        urlencoded = urllib.urlencode(form_dict)
        print urlencoded
        conn = httplib2.Http(disable_ssl_certificate_validation=True)
        url = settings.VIVEUM_PAYMENT.get('ORDER_STANDARD_URL')
        httpresp, content = conn.request(url, method='POST', body=urlencoded,
            headers={'Content-type': 'application/x-www-form-urlencoded'})
        self.assertEqual(httpresp.status, 200, 'PSP failed to answer with HTTP code 200')
        return content

    def _credit_card_payment(self, htmlsource, cc_number):
        """
        Our PSP returned an HTML page containing a form with hidden input fields
        and with text fields to enter the credit card number. Use these fields
        to simulate a POST request which actually performes the payment.
        """
        dom = PyQuery(htmlsource)
        elements = dom('input[type=hidden]')
        self.assertTrue(elements, 'No hidden input fields found in form')
        elements.extend(dom('input[name=Ecom_Payment_Card_Name]'))
        values = dict((elem.name, elem.value) for elem in elements)
        values.update({
            'Ecom_Payment_Card_Number': cc_number,
            'Ecom_Payment_Card_ExpDate_Month': '12',
            'Ecom_Payment_Card_ExpDate_Year': '2029',
            'Ecom_Payment_Card_Verification': '123',
        })
        form = dom('form[name=OGONE_CC_FORM]')
        urlencoded = urllib.urlencode(values)
        print urlencoded
        conn = httplib2.Http(disable_ssl_certificate_validation=True)
        url = form.attr('action')
        httpresp, content = conn.request(url, method='POST', body=urlencoded,
            headers={'Content-type': 'application/x-www-form-urlencoded'})
        self.assertEqual(httpresp.status, 200, 'PSP failed to answer with HTTP code 200')
        return content

    def _extract_redirection_path(self, htmlsource):
        dom = PyQuery(htmlsource)
        form = dom('table table form')
        self.assertTrue(form, 'Redirect form not found in DOM')
        return urlparse.urlparse(form.attr('action'))

    def _return_success_view(self, htmlsource):
        urlobj = self._extract_redirection_path(htmlsource)
        self.assertEqual(urlobj.path, reverse('viveum_accept'))
        data = dict(urlparse.parse_qsl(urlobj.query))
        httpresp = self.client.get(urlobj.path, data, follow=True)
        self.assertEqual(len(httpresp.redirect_chain), 1, 'No redirection after receiving payment status')
        urlobj = urlparse.urlparse(httpresp.redirect_chain[0][0])
        self.assertEqual(httpresp.status_code, 200, 'Merchant failed to finish payment receivement')
        self.assertEqual(resolve(urlobj.path).url_name, 'thank_you_for_your_order')

    def test_visa_payment(self):
        payment_form = self._send_transaction_data()
        self._save_htmlsource('payment_form', payment_form)
        authorized_form = self._credit_card_payment(payment_form, '4111111111111111')
        self._save_htmlsource('authorized_form', authorized_form)
        self._return_success_view(authorized_form)
        order = Order.objects.get(pk=self.order.id)
        # TODO: self.assertEqual(order.status, Order.COMPLETED)
        confirmation = Confirmation.objects.get(order__pk=self.order.id)
        self.assertTrue(str(confirmation.status).startswith('5'))

    def _save_htmlsource(self, name, htmlsource):
        if self.save_received_data:
            f = open('psp-%s.tmp.html' % name, 'w')
            f.write(htmlsource)
            f.close()
