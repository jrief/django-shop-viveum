====================
django-shop-viveum
====================

This module is a payment backend module for django-SHOP (https://github.com/divio/django-shop),
using Viveum (https://viveum.v-psp.com) as the shops payment service provider.
It can be used for credit card and other kind of payments.

Currently only payment methods are implemented, which do not require a PCI DSS certification
(https://www.pcisecuritystandards.org/) for your shop. This means that your shop never "sees" the
credit card numbers, and thus can not store and in consequence abuse them.

Installation
============
Using pip::

    pip install django-shop-viveum

Viveum Configuration
====================

Get in touch with Viveum and ask for a test account. They will send you an identifier
and a password. Use the given values and log into
https://viveum.v-psp.com/ncol/test/admin_viveum.asp
this will bring you into an admin backend. All the relevant settings required to configure this
module can be fetched from the menu item
**Configuration > Technical information > Global security parameters**::
    Hash algorithm: SHA-1
    Character encoding: UTF-8
    Enable JavaScript check on template: Yes
    Allow usage of static template: Yes

Generate a 16 digit SHA-IN and a 12 digit SHA-OUT random pass phrase (``base64``
and ``/dev/urandom`` are your friends) and copy them into the given fields at
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

    SHA-OUT pass phrase: (as above)

Test the Configuration
======================
In order to run the unit tests, you must install an additional Python package,
which is not required for normal operation::

    pip install requests

Unfortunately there might be an unresolved issue with SSL on requests. Please read
docs/ssl-problem.rst for details.

Run ``./runtests.sh``.
If everything worked fine, you should receive two emails, one for a successful,
and one for a declined payment.
If there is an error, check the error log at the Viveum admin interface.

Test cards
==========
During manual testing, you may not want to use a real credit card number. Here are a few official
credit card numbers for testing:

* VISA: 4111111111111111 with any expiry date in the future and any 3 digit security code.
* A number of a "stolen" card: 4111113333333333 – payment shall be refused.


Use these settings in your shop Configuration
=============================================
If all tests work fine, use these tested settings for your production environment.

* In Viveums admin interface, transfer your test account settings to production.
* In your project setting.py
  * add ``viveum``, to INSTALLED_APPS.
  * add ``synthesa.payment.backends.ViveumPaymentBackend`` to SHOP_PAYMENT_BACKENDS.
  * copy the content of ``tests/viveum_settings.py`` into the ``settings.py`` file of
    your project. In dict ``VIVEUM_PAYMENT`` change 
    ``ORDER_STANDARD_URL`` to ``https://viveum.v-psp.com/ncol/prod/orderstandard_UTF8.asp``

CHANGES
=======

* 0.1.0: First release to the public.
* 0.3.2: Can distinguish between return status 5 and 9 and accept both.
