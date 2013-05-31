
raise Exception('Please read the docs on how to set up this file')

VIVEUM_PAYMENT = {
    'ORDER_STANDARD_URL': 'https://viveum.v-psp.com/ncol/test/orderstandard_UTF8.asp',
    'PSPID': 'my_account_id',
    'ORDER_DESCRIPTION': 'Your order %s at Awesome-Shop',  # text to be shown on the acquirers account statement
    'SHA1_IN_SIGNATURE': 'a_16_digit_secret',
    'SHA1_OUT_SIGNATURE': '12_digit_secret',
    'CURRENCY': 'EUR',
    'LANGUAGE': 'en_US',
    'TITLE': 'Viveum PSP Unittest',
}
