# -*- coding: utf-8 -*-
import requests
import time
import urlparse
from pyquery.pyquery import PyQuery
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
        self.save_received_data = False  # if True, leave a hard copy of the html sources received from the PSP
        current_site = Site.objects.get_current()
        current_site.domain = settings.HOST_NAME
        current_site.save()
        self.create_fake_order()
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
        self.add_product_to_cart()
        self.checkout()

    def tearDown(self):
        time.sleep(10)  # this keeps the live test server running for a while

    def add_product_to_cart(self):
        product = DiaryProduct(isbn='1234567890', number_of_pages=100, name='test',
            slug='test', active=True, unit_price=Decimal('1.23'))
        product.save()
        self.cart = get_or_create_cart(self.request, True)
        self.cart.add_product(product, 1)
        self.cart.save()

    def checkout(self):
        # add address information
        post_data = {
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
        response = self.client.post(reverse('checkout_selection'), post_data, follow=True)
        urlobj = urlparse.urlparse(response.redirect_chain[0][0])
        self.assertEqual(resolve(urlobj.path).url_name, 'checkout_shipping')
        urlobj = urlparse.urlparse(response.redirect_chain[1][0])
        self.assertEqual(resolve(urlobj.path).url_name, 'flat')
        self.order = self.viveum_backend.shop.get_order(self.request)

    def create_fake_order(self):
        """
        Create a fake order with a random order id, so that the following real
        order does not start with 1. Otherwise this could cause errors if this
        test is invoked multiple times.
        """
        order_id = random.randint(100001, 999999)
        Order.objects.create(id=order_id, status=Order.CANCELLED)

    def send_transaction_data(self):
        """
        Send data fields for the current transaction to the PSP using method POST.
        """
        form_dict = self.viveum_backend.get_form_dict(self.request)
        self.viveum_backend.sign_form_dict(form_dict)
        url = settings.VIVEUM_PAYMENT.get('ORDER_STANDARD_URL')
        response = requests.post(url, data=form_dict, verify=True)
        self.assertEqual(response.status_code, 200, 'PSP failed to answer with HTTP code 200')
        return response.content

    def credit_card_payment(self, htmlsource, cc_number):
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
        url = form.attr('action')
        response = requests.post(url, data=values, verify=True)
        self.assertEqual(response.status_code, 200, 'PSP failed to answer with HTTP code 200')
        return response.content

    def extract_redirection_path(self, htmlsource):
        dom = PyQuery(htmlsource)
        form = dom('table table form')
        self.assertTrue(form, 'Redirect form not found in DOM')
        return urlparse.urlparse(form.attr('action'))

    def process_success_view(self, htmlsource):
        urlobj = self.extract_redirection_path(htmlsource)
        self.assertEqual(urlobj.path, reverse('viveum_accept'))
        data = dict(urlparse.parse_qsl(urlobj.query))
        httpresp = self.client.get(urlobj.path, data, follow=True)
        self.assertEqual(len(httpresp.redirect_chain), 1, 'No redirection after receiving payment status')
        urlobj = urlparse.urlparse(httpresp.redirect_chain[0][0])
        self.assertEqual(httpresp.status_code, 200, 'Merchant failed to finish payment receivement')
        self.assertEqual(resolve(urlobj.path).url_name, 'thank_you_for_your_order')

    def process_decline_view(self, htmlsource):
        dom = PyQuery(htmlsource)
        form = dom('#form3')
        self.assertTrue(form, 'No <form id="#form1"> found in html output')
        elements = form.find('input')
        values = dict((elem.name, elem.value) for elem in elements)
        values.update({'cancel': 'Cancel'})
        url = form.attr('action')
        response = requests.post(url, data=values, verify=True)
        self.assertEqual(response.status_code, 200, 'PSP did not accept payment cancellation')
        self.save_htmlsource('decline_form', response.content)
        # in response check for string 'Cancelled'
        dom = PyQuery(response.content)
        tables = dom('table.ncoltable1')
        self.assertEqual(len(tables), 3)
        self.assertEqual(tables.eq(1).find('h3').text(), 'Cancelled')
        form = tables.eq(2).find('form')
        urlobj = urlparse.urlparse(form.attr('action'))
        data = dict(urlparse.parse_qsl(urlobj.query))
        httpresp = self.client.get(urlobj.path, data, follow=True)
        self.assertEqual(len(httpresp.redirect_chain), 2, 'No redirection after declining payment')
        urlobj = urlparse.urlparse(httpresp.redirect_chain[1][0])
        self.assertEqual(httpresp.status_code, 200)
        self.assertEqual(resolve(urlobj.path).url_name, 'viveum')

    def save_htmlsource(self, name, htmlsource):
        if self.save_received_data:
            f = open('psp-%s.tmp.html' % name, 'w')
            f.write(htmlsource)
            f.close()

    def test_visa_payment(self):
        """
        With a valid credit card number, the payment is accepted.
        The payment module creates a confirmation object, which declares this
        payment as successful. The corresponding order object is set to status
        COMPLETED.
        """
        payment_form = self.send_transaction_data()
        self.save_htmlsource('payment_form', payment_form)
        authorized_form = self.credit_card_payment(payment_form, '4111111111111111')
        self.save_htmlsource('authorized_form', authorized_form)
        self.process_success_view(authorized_form)
        order = Order.objects.get(pk=self.order.id)  # Our order
        self.assertEqual(order.status, Order.COMPLETED)
        confirmation = Confirmation.objects.get(order__pk=self.order.id)  # The PSP's confirmation
        self.assertEqual(confirmation.brand, 'VISA')
        self.assertEqual(confirmation.amount, order.order_total)

    def test_declined_payment(self):
        """
        With an invalid credit card number, the payment is declined.
        The payment module creates a confirmation object, which cancels this
        payment.
        """
        payment_form = self.send_transaction_data()
        self.save_htmlsource('payment_form', payment_form)
        authorized_form = self.credit_card_payment(payment_form, '4111113333333333')
        self.save_htmlsource('authorized_form', authorized_form)
        self.process_decline_view(authorized_form)
        confirmation = Confirmation.objects.get(order__pk=self.order.id)  # The PSP's confirmation
        self.assertEqual(confirmation.brand, 'VISA')
        self.assertTrue(str(confirmation.status).startswith('1'))

    def test_template(self):
        httpresp = self.client.get(reverse('viveum_template'))
        self.assertContains(httpresp, '$$$PAYMENT ZONE$$$')
