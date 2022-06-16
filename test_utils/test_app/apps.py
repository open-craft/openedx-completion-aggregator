"""
Test App Django application initialization.
"""

from __future__ import absolute_import, unicode_literals

from django.apps import AppConfig


class TestAppConfig(AppConfig):
    """
    Configuration for the test_app.
    """

    name = 'test_utils.test_app'
