"""
Initialize celery for testing purposes.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')

app = Celery('test_project', broker='redis://')
app.conf.update(CELERY_ACCEPT_CONTENT=['json'])
app.conf.update(CELERY_ALWAYS_EAGER=True)
app.autodiscover_tasks(['completion_aggregator'])
