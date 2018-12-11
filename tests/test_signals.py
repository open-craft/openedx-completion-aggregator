"""
Tests that exercise completion signals and handlers.

Demonstrate that the signals connect the handler to the aggregated model.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from mock import patch
from opaque_keys.edx.keys import CourseKey, UsageKey

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from completion.models import BlockCompletion
from completion_aggregator.batch import perform_aggregation
from completion_aggregator.models import Aggregator, StaleCompletion
from completion_aggregator.signals import cohort_updated_handler, course_published_handler, item_deleted_handler
from test_utils.compat import StubCompat


class SignalsTestCase(TestCase):
    """
    Test that the the post-save signal handler receives the signal when the aggregated model
    is saved
    """
    def setUp(self):
        super(SignalsTestCase, self).setUp()
        user_model = get_user_model()
        self.user = user_model.objects.create()
        self.extra_users = [
            user_model.objects.get_or_create(username='user0')[0],
            user_model.objects.get_or_create(username='user1')[0],
            user_model.objects.get_or_create(username='user2')[0],
        ]

    @patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
    def test_basic(self, mock_task):
        course_key = CourseKey.from_string('edX/test/2018')
        block_key = UsageKey.from_string('i4x://edX/test/video/friday')
        completable = BlockCompletion(
            user=self.user,
            course_key=course_key,
            block_key=block_key,
            completion=1.0,
            modified=now()
        )
        mock_task.reset()
        completable.save()
        assert StaleCompletion.objects.filter(
            username=self.user.username,
            course_key=course_key,
            block_key=block_key
        ).exists()
        mock_task.assert_not_called()
        perform_aggregation()
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
        # One extra to ensure we don't submit extra tasks.
        Aggregator.objects.submit_completion(
            user=self.extra_users[0],
            course_key=course_key,
            block_key=course_key.make_usage_key('course', 'course'),
            aggregation_name='course',
            earned=1.0,
            possible=1.0,
            last_modified=now(),
        )

    def test_course_published_handler(self):
        course_key = CourseKey.from_string('edX/test/2018')
        self.setup_active_users(course_key)
        course_published_handler(course_key)
        self.assertEqual(
            StaleCompletion.objects.filter(course_key=course_key, force=True).count(),
            len(self.extra_users),
        )

    def test_item_deleted_handler(self):
        block_key = UsageKey.from_string('block-v1:edX+test+2018+type@problem+block@one-plus-one')
        self.setup_active_users(block_key.course_key)
        item_deleted_handler(block_key, self.user.id)
        stale_qs = StaleCompletion.objects.filter(course_key=block_key.course_key, force=True)
        assert stale_qs.count() == len(self.extra_users)

    def test_cohort_signal_handler(self):
        course_key = CourseKey.from_string('course-v1:edX+test+2018')
        user = get_user_model().objects.create(username='deleter')
        with patch('completion_aggregator.core.compat', StubCompat([])):
            cohort_updated_handler(user, course_key)
            assert StaleCompletion.objects.filter(username=user.username, course_key=course_key, force=True).exists()
