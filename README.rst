====================
django-shop-viveum
====================

This module is a payment backend module for django-SHOP, using Viveum 
(https://viveum.v-psp.com) as the shops payment service provider. It can be
used for credit card and other kind of payments.

Currently only payment methods are implemented, which do not require a PCI DSS
certification (https://www.pcisecuritystandards.org/) for your shop.
This means that your shop never "sees" the credit card numbers.
With this module your customer "leaves" your shop to enter his credit card numbers
on the Viveum site secured by SSL. Afterwards the customer is redirected back to
the shop using a special URL, which transports the payment confirmation using a
signature technique.

Installation
============
Using pip::

    pip install django-shop-viveum

Viveum Configuration
====================

Get in touch with Viveum and ask for a test account. They will send you an identifier
and a password. Use the given values and log into https://viveum.v-psp.com/ncol/test/admin_viveum.asp
this will bring you into a old-fashioned admin environment. All the relevant settings 
required to configure this module can be fetched from the menu item
**Configuration > Technical information > Global security parameters**::
    Hash algorithm: SHA-1
    Character encoding: UTF-8
    Enable JavaScript check on template: Yes
    Allow usage of static template: Yes

In your local shell, generate a SHA-IN pass phrase::

    $ base64 -b16 < /dev/urandom | head -n1

and copy it into the given field at
**Configuration > Technical information > Data and origin verification > SHA-IN pass phrase**::

**Configuration > Technical information > Transaction feedback**::
    YES, I would like to receive transaction feedback parameters on the redirection URLs.
    YES, I would like VIVEUM to display a short text to the customer on the secure payment page
    Timing of the request: Always online
    Request method: GET
    Dynamic e-Commerce parameters Selected:
        ACCEPTANCE
        AMOUNT
        BRAND
        CARDNO
        CN
        CURRENCY
        IP
        NCERROR
        ORDERID
        PAYID
        STATUS

Shop Configuration
==================

In settings.py

* Add ‘viveum', to INSTALLED_APPS.
* Add 'synthesa.payment.backends.ViveumPaymentBackend' to SHOP_PAYMENT_BACKENDS.
* Add the configuration dictionary::

    VIVEUM_PAYMENT = {
        'ORDER_STANDARD_URL': 'https://viveum.v-psp.com/ncol/%s/orderstandard_UTF8.asp' % ('prod' if not DEBUG else 'test'),
        'PSPID': 'your_PSPID',  # the same you use to log into https://viveum.v-psp.com/ncol/test/admin_viveum.asp
        'ORDER_DESCRIPTION': 'Your order (%s) at Awesome Shop',
        'SHA1_IN_SIGNATURE': 'some_hash_value',
        'SHA1_OUT_SIGNATURE': 'some_hash_value',
        'CURRENCY': 'EUR',
        'LANGUAGE': 'en_EN', # 
        'TITLE': 'Greeting at Viveum during payment',
    }


Test the Configuration
======================

In order to run the unit tests, you must install an additional Python package,
which is not required for normal operation::

    pip install httplib2==0.7.6

Unfortunately there is a still unresolved issue with SSL on httplib2. Therefore you
must make some modifications on httplib2. Install version 0.7.6, change into your
Python site-packages directory and apply the following patch file as found in docs::

    patch -p0 < docs/httplib2-0.7.6-ssl.patch

Change the values for VIVEUM_PAYMENT in ``tests/testapp/settings.py`` according 
to the chosen configuration. The run ``./runtests.sh``. If everything worked fine,
you should receive two emails, one for a successful, and one for a declined payment.
If there is an error, check the error log at the Viveum admin interface.

CHANGES
=======

0.1.0
First release to the public, which allows transaction mode 'eCommerce'.
