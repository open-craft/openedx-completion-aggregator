"""
Test the aggregator functions directly.
"""

# Redefined outer names are explicitly used by pytest fixtures.
# pylint: disable=redefined-outer-name

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import six
from mock import patch
from opaque_keys.edx.keys import CourseKey
from xblock.core import XBlock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from completion.models import BlockCompletion
from completion_aggregator.batch import perform_aggregation, perform_cleanup
from completion_aggregator.models import StaleCompletion
from test_utils.compat import StubCompat
from test_utils.xblocks import CourseBlock, HTMLBlock, OtherAggBlock


@pytest.fixture
def users(django_user_model):
    """
    Create two users.
    """
    return [
        django_user_model.objects.create(username='Spy'),
        django_user_model.objects.create(username='VsSpy'),
    ]


@override_settings(COMPLETION_AGGREGATOR_ASYNC_AGGREGATION=False)
@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_synchronous_aggregation(mock_task, users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    for user in users:
        BlockCompletion.objects.create(
            user=user,
            course_key=course_key,
            block_key=course_key.make_usage_key('video', 'how-to-open-craft'),
            completion=0.75,
        )

        BlockCompletion.objects.create(
            user=user,
            course_key=course_key,
            block_key=course_key.make_usage_key('video', 'how-not-to-open-craft'),
            completion=1.0,
        )
        # Prevent enrollments from being aggregated multiple times.
        StaleCompletion.objects.update(resolved=True)

    assert mock_task.call_count == 4  # Called once per created BlockCompletion


@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_with_multiple_batches(mock_task, users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    block_keys = [
        course_key.make_usage_key('video', 'video-1'),
        course_key.make_usage_key('video', 'video-2'),
    ]
    for user in users:
        for block_key in block_keys:
            BlockCompletion.objects.create(
                user=user,
                course_key=course_key,
                block_key=block_key,
                completion=1.0,
            )
    perform_aggregation(batch_size=1, limit=2)
    assert mock_task.call_count == 1
    # Order of block_keys is not defined
    mock_task.call_args[1]['kwargs']['block_keys'] = set(mock_task.call_args[1]['kwargs']['block_keys'])
    assert mock_task.call_args[1]['kwargs'] == {
        'username': users[1].username,
        'course_key': six.text_type(course_key),
        'block_keys': {six.text_type(key) for key in block_keys},
        'force': False,
    }


@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_with_stale_completions(mock_task, users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    for user in users:
        BlockCompletion.objects.create(
            user=user,
            course_key=course_key,
            block_key=course_key.make_usage_key('video', 'how-to-open-craft'),
            completion=0.75,
        )
        BlockCompletion.objects.create(
            user=user,
            course_key=course_key,
            block_key=course_key.make_usage_key('video', 'how-not-to-open-craft'),
            completion=1.0,
        )
    perform_aggregation()
    assert mock_task.call_count == 2  # Called once for each user


@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_with_full_course_stale_completion(mock_task, users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    for user in users:
        StaleCompletion.objects.create(
            username=user.username,
            course_key=course_key,
            block_key=None,
        )
        StaleCompletion.objects.create(
            username=user.username,
            course_key=course_key,
            block_key=course_key.make_usage_key('video', 'how-to-open-craft'),
        )
    perform_aggregation()
    assert mock_task.call_count == 2  # Called once for each user


@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_with_no_completions(mock_task, users):  # pylint: disable=unused-argument
    perform_aggregation()
    assert mock_task.call_count == 0


@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_with_no_blocks(mock_task, users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    StaleCompletion.objects.create(username=users[0].username, course_key=course_key, block_key=None, force=True)
    perform_aggregation()
    assert mock_task.call_count == 1


@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_lock(mock_task, users):
    """Ensure that only one batch aggregation is running at the moment."""
    cache.add(
        settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK,
        True,
        settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS
    )
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    StaleCompletion.objects.create(username=users[0].username, course_key=course_key, block_key=None, force=True)
    perform_aggregation()
    cache.delete(settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK)
    assert mock_task.call_count == 0


def test_plethora_of_stale_completions(users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')

    with patch('completion_aggregator.batch.MAX_KEYS_PER_TASK', new=3) as max_keys:
        for i in range(max_keys + 1):
            StaleCompletion.objects.create(
                username=users[0].username,
                course_key=course_key,
                block_key=course_key.make_usage_key('chapter', 'chapter-{}'.format(i)),
            )
        with patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async') as mock_task:
            perform_aggregation()
    mock_task.assert_called_once_with(
        kwargs={
            'username': users[0].username,
            'course_key': six.text_type(course_key),
            'block_keys': [],
            'force': False,
        },
    )
    assert mock_task.call_count == 1


def test_cleanup_and_lock(users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    StaleCompletion.objects.create(username=users[0].username, course_key=course_key, block_key=None, force=True)
    cache.add(
        settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK,
        True,
        settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS
    )
    perform_cleanup()
    assert StaleCompletion.objects.count() == 1

    cache.delete(settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK)
    perform_cleanup()
    assert StaleCompletion.objects.count() == 0


class StaleCompletionResolutionTestCase(TestCase):
    """
    XBlock.register_temp_plugin decorator breaks pytest fixtures, so we
    do this one test as a unittest test case.

    TODO: Update the XBlock.register_temp_plugin decorator to play nice with
    pytest.
    """
    def setUp(self):
        super(StaleCompletionResolutionTestCase, self).setUp()
        self.users = [
            get_user_model().objects.create(username='Spy'),
            get_user_model().objects.create(username='VsSpy'),
        ]

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'vertical')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    @pytest.mark.django_db
    def test_stale_completion_resolution(self):
        # Verify that all stale completions get resolved, even if the course
        # is not present in the modulestore
        course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
        for user in self.users:
            StaleCompletion.objects.create(username=user.username, course_key=course_key, block_key='', force=False)
            StaleCompletion.objects.create(username=user.username, course_key='not/a/course', block_key='', force=False)
        assert not StaleCompletion.objects.filter(resolved=True).exists()
        assert StaleCompletion.objects.filter(resolved=False).exists()
        with compat_patch(course_key):
            perform_aggregation()
        assert StaleCompletion.objects.filter(resolved=True).exists()
        assert not StaleCompletion.objects.filter(resolved=False).exists()
        for user in self.users:
            StaleCompletion.objects.create(username=user.username, course_key=course_key, block_key=None, force=False)
        perform_cleanup()
        assert not StaleCompletion.objects.filter(resolved=True).exists()
        assert StaleCompletion.objects.filter(resolved=False).exists()


def compat_patch(course_key):
    """
    Patch compat with a stub including a simple course.
    """
    return patch('completion_aggregator.core.compat', StubCompat([
        course_key.make_usage_key('course', 'course'),
        course_key.make_usage_key('vertical', 'course-vertical'),
        course_key.make_usage_key('html', 'course-vertical-html'),
    ]))
