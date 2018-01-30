"""
Tests that exercise completion signals and handlers.

Demonstrate that the signals connect the handler to the aggregated model.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from mock import patch
from opaque_keys.edx.keys import CourseKey, UsageKey

from django.contrib.auth.models import User
from django.test import TestCase

from test_utils.test_app.models import Completable


class SignalCalledTestCase(TestCase):
    """
    Test that the the signal handler receives the signal when the aggregated model
    is saved
    """
    def setUp(self):
        self.user = User.objects.create()

    @patch('completion_aggregator.signals.log.info')
    def test_basic(self, mock_log):
        completable = Completable(
            user=self.user,
            course_key=CourseKey.from_string('edX/test/2018'),
            block_key=UsageKey.from_string('i4x://edX/test/video/friday'),
            completion=1.0,
        )
        completable.save()
        mock_log.assert_called_once()
