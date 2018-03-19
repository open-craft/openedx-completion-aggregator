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


AUTH_USER_MODEL = 'auth.User'
CELERY_ALWAYS_EAGER = True
COMPLETION_AGGREGATOR_BLOCK_TYPES = {'course', 'chapter'}
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
DEBUG = True
INSTALLED_APPS = (
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'completion_aggregator',
    'completion',
    'oauth2_provider',
    'test_utils.test_app',
)

LOCALE_PATHS = [root('completion_aggregator', 'conf', 'locale')]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'PAGE_SIZE': 10,
}

ROOT_URLCONF = 'completion_aggregator.urls'
SECRET_KEY = 'insecure-secret-key'
USE_TZ = True

# pylint: disable=unused-import,wrong-import-position
from test_utils.test_app import celery  # isort:skip
