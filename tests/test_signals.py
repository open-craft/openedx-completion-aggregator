"""
Tests that exercise completion signals and handlers.

Demonstrate that the signals connect the handler to the aggregated model.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from mock import call, patch
from opaque_keys.edx.keys import CourseKey, UsageKey

import six
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from completion.models import BlockCompletion
from completion_aggregator.signals import cohort_updated_handler, course_published_handler, item_deleted_handler
from test_utils.compat import StubCompat


class SignalsTestCase(TestCase):
    """
    Test that the the post-save signal handler receives the signal when the aggregated model
    is saved
    """
    def setUp(self):
        self.user = get_user_model().objects.create()

    @patch('completion_aggregator.tasks.update_aggregators.apply_async')
    def test_basic(self, mock_task):
        completable = BlockCompletion(
            user=self.user,
            course_key=CourseKey.from_string('edX/test/2018'),
            block_key=UsageKey.from_string('i4x://edX/test/video/friday'),
            completion=1.0,
            modified=now()
        )
        completable.save()
        mock_task.assert_called_once()

    @patch('completion_aggregator.tasks.update_aggregators.apply_async')
    def test_course_published_handler(self, mock_task):
        course_key = CourseKey.from_string('edX/test/2018')
        with patch('completion_aggregator.signals.compat', StubCompat()) as mock_compat:
            course_published_handler(course_key)
            users = mock_compat.get_enrolled_users(course_key)
            self.assertGreater(len(users), 0)
            print(mock_task.mock_calls)
            mock_task.assert_has_calls(
                [call(
                    (), dict(username=user.username, course_key=six.text_type(course_key), force=True),
                ) for user in users],
                any_order=True,
            )

    @patch('completion_aggregator.tasks.update_aggregators.apply_async')
    def test_item_deleted_handler(self, mock_task):
        block_key = UsageKey.from_string('block-v1:edX+test+2018+type@problem+block@one-plus-one')
        user = get_user_model().objects.create(username='deleter')
        with patch('completion_aggregator.signals.compat', StubCompat()) as mock_compat:
            item_deleted_handler(block_key, user.id)
            users = mock_compat.get_enrolled_users(block_key.course_key)
            self.assertGreater(len(users), 0)
            print(mock_task.mock_calls)
            mock_task.assert_has_calls(
                [call(
                    (), dict(username=user.username, course_key=six.text_type(block_key.course_key), force=True),
                ) for user in users],
                any_order=True,
            )

    @patch('completion_aggregator.tasks.update_aggregators.apply_async')
    def test_cohort_signal_handler(self, mock_task):
        course_key = CourseKey.from_string('course-v1:edX+test+2018')
        user = get_user_model().objects.create(username='deleter')
        with patch('completion_aggregator.signals.compat', StubCompat()):
            cohort_updated_handler(user, course_key)
            mock_task.assert_called_once_with(
                (), dict(username=user.username, course_key=six.text_type(course_key), force=True)
            )
