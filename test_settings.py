"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from __future__ import absolute_import, unicode_literals

from os import environ
from os.path import abspath, dirname, join


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


ALLOWED_COMPLETION_AGGREGATOR_EVENT_TYPES = {
    "progress": [
        "course",
        "chapter",
        "sequential",
        "vertical",
    ],
    "completion": [
        "course",
        "chapter",
        "sequential",
        "vertical",
    ]
}
AUTH_USER_MODEL = 'auth.User'
CELERY_ALWAYS_EAGER = True
COMPLETION_AGGREGATOR_BLOCK_TYPES = {'course', 'chapter', 'sequential'}
COMPLETION_AGGREGATOR_ASYNC_AGGREGATION = True
COMPLETION_AGGREGATOR_AGGREGATION_LOCK = 'COMPLETION_AGGREGATOR_AGGREGATION_LOCK'
COMPLETION_AGGREGATOR_CLEANUP_LOCK = 'COMPLETION_AGGREGATOR_CLEANUP_LOCK'
COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS = 1800
COMPLETION_AGGREGATOR_CLEANUP_LOCK_TIMEOUT_SECONDS = 900
COMPLETION_AGGREGATOR_AGGREGATE_UNRELEASED_BLOCKS = False

DATABASES = {
    'default': {
        'ATOMIC_REQUESTS': True,
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'completion_aggregator_test',
        'HOST': environ.get('EDXAGG_MYSQL_HOST', '127.0.0.1'),
        'PORT': int(environ.get('EDXAGG_MYSQL_PORT', 3307)),
        'USER': environ.get('EDXAGG_MYSQL_USER', 'root'),
        'PASSWORD': environ.get('EDXAGG_MYSQL_PASSWORD', 'rootpw'),
        'OPTIONS': {
            'init_command': "SET sql_mode='ALLOW_INVALID_DATES'",
        }
    }
}
DEBUG = True
INSTALLED_APPS = (
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.admin',
    'completion_aggregator',
    'completion',
    'oauth2_provider',
    'waffle',
    'test_utils.test_app',
    'eventtracking.django.apps.EventTrackingConfig',
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
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
    },
]
USE_TZ = True

EVENT_TRACKING_ENABLED = True

# pylint: disable=unused-import,wrong-import-position
from test_utils.test_app import celery  # isort:skip
