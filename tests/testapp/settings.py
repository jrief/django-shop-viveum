# Django settings for unit test project.
from utils import what_is_my_ip

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'test.sqlite',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    },
}

SITE_ID = 1

# The hostname of this testing server visible to the outside world
HOST_NAME = what_is_my_ip()

STATIC_URL = '/static/'

SECRET_KEY = 'h2%uf!luks79rw^4!5%q#v2znc87g_)@^jf1og!04@&&tsf7*9'

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
)

ROOT_URLCONF = 'testapp.urls'

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'polymorphic',  # We need polymorphic installed for the shop
    'shop',  # The django SHOP application
    'shop.addressmodel',
    'viveum',
    'testapp',  # the test project application
)

SHOP_SHIPPING_BACKENDS = (
    'shop.shipping.backends.flat_rate.FlatRateShipping',
)

SHOP_PAYMENT_BACKENDS = (
    'viveum.offsite_backend.OffsiteViveumBackend',
)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'simple': {
            'format': '%(levelname)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'viveum.offsite_backend': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    }
}

try:
    import viveum_settings
except ImportError:
    print """
    -------------------------------------------------------------------------
    You need to create a local_settings.py file which needs to contain your
    private configurations at Viveum/Ogone.
    Use docs/local_settings.py as a reference to start with.
    -------------------------------------------------------------------------
    """
    import sys
    sys.exit(1)
else:
    for attr in dir(viveum_settings):
        globals()[attr] = getattr(viveum_settings, attr)
