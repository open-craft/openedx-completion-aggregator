"""
Tests that exercise completion signals and handlers.

Demonstrate that the signals connect the handler to the aggregated model.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import six
from mock import call, patch
from opaque_keys.edx.keys import CourseKey, UsageKey

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from completion.models import BlockCompletion
from completion_aggregator.models import Aggregator
from completion_aggregator.signals import cohort_updated_handler, course_published_handler, item_deleted_handler
from test_utils.compat import StubCompat


class SignalsTestCase(TestCase):
    """
    Test that the the post-save signal handler receives the signal when the aggregated model
    is saved
    """
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create()
        self.extra_users = [
            user_model.objects.get_or_create(username='user0')[0],
            user_model.objects.get_or_create(username='user1')[0],
            user_model.objects.get_or_create(username='user2')[0],
        ]

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

    def setup_active_users(self, course_key):
        """
        Setup self.extra_users as having been active in the course.

        The presence of aggregators under their name will cause them to be
        recalculated when the course is modified.

        this implementation returns three users, named "user0", "user1", and
        "user2".
        """
        for user in self.extra_users:
            Aggregator.objects.submit_completion(
                user=user,
                course_key=course_key,
                block_key=course_key.make_usage_key('vertical', 'intro'),
                aggregation_name='vertical',
                earned=1.0,
                possible=1.0,
                last_modified=now(),
            )

    @patch('completion_aggregator.tasks.update_aggregators.apply_async')
    def test_course_published_handler(self, mock_task):
        course_key = CourseKey.from_string('edX/test/2018')
        self.setup_active_users(course_key)
        mock_task.reset_mock()
        course_published_handler(course_key)
        self.assertEqual(mock_task.call_count, len(self.extra_users))
        mock_task.assert_has_calls(
            [call(
                (), dict(username=user.username, course_key=six.text_type(course_key), force=True),
            ) for user in self.extra_users],
            any_order=True,
        )

    @patch('completion_aggregator.tasks.update_aggregators.apply_async')
    def test_item_deleted_handler(self, mock_task):
        block_key = UsageKey.from_string('block-v1:edX+test+2018+type@problem+block@one-plus-one')
        self.setup_active_users(block_key.course_key)
        mock_task.reset_mock()
        item_deleted_handler(block_key, self.user.id)
        mock_task.assert_has_calls(
            [call(
                (), dict(username=user.username, course_key=six.text_type(block_key.course_key), force=True),
            ) for user in self.extra_users],
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
