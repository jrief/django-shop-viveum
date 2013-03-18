# -*- coding: utf-8 -*-
from django.conf import settings as _settings


def viveum(request):
    """
    Adds additional context variables to the default context.
    """
    return {
        'VIVEUM_ORDER_STANDARD_URL': _settings.VIVEUM_PAYMENT.get('ORDER_STANDARD_URL'),
    }

