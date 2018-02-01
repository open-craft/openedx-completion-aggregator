"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from __future__ import absolute_import, unicode_literals

from os.path import abspath, dirname, join


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


USE_TZ = True
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'default.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}

INSTALLED_APPS = (
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'completion_aggregator',
    'completion',
    'test_utils.test_app',
)

LOCALE_PATHS = [
    root('completion_aggregator', 'conf', 'locale'),
]

ROOT_URLCONF = 'completion_aggregator.urls'

SECRET_KEY = 'insecure-secret-key'

COMPLETION_AGGREGATOR_BLOCK_TYPES = {'course', 'chapter'}

CELERY_ALWAYS_EAGER = True

from test_utils.test_app import celery  # isort:skip
