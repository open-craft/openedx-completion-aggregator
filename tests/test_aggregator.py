"""
Test the aggregator functions directly.
"""

# Redefined outer names are explicitly used by pytest fixtures.
# pylint: disable=redefined-outer-name

import pytest
from mock import patch
from opaque_keys.edx.keys import CourseKey
from xblock.core import XBlock

from django.contrib.auth import get_user_model
from django.test import override_settings

from completion.models import BlockCompletion
from completion_aggregator.aggregator import perform_aggregation, perform_cleanup
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


@pytest.mark.django_db
@patch('completion_aggregator.tasks.aggregation_tasks.update_aggregators.apply_async')
def test_with_no_blocks(mock_task, users):
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    StaleCompletion.objects.create(username=users[0].username, course_key=course_key, block_key=None, force=True)
    perform_aggregation()
    assert mock_task.call_count == 1


def compat_patch(course_key):
    return patch('completion_aggregator.tasks.aggregation_tasks.compat', StubCompat([
        course_key.make_usage_key('course', 'course'),
        course_key.make_usage_key('vertical', 'course-vertical'),
        course_key.make_usage_key('html', 'course-vertical-html'),
    ]))


@XBlock.register_temp_plugin(CourseBlock, 'course')
@XBlock.register_temp_plugin(OtherAggBlock, 'vertical')
@XBlock.register_temp_plugin(HTMLBlock, 'html')
@pytest.mark.django_db
def test_stale_completion_resolution():
    user_objs = users(get_user_model())  # XBlock.register_temp_plugin decorator breaks pytest fixtures
    course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
    for user in user_objs:
        StaleCompletion.objects.create(username=user.username, course_key=course_key, block_key=None, force=True)
    assert not StaleCompletion.objects.filter(resolved=True).exists()
    assert StaleCompletion.objects.filter(resolved=False).exists()
    with compat_patch(course_key):
        perform_aggregation()
    assert StaleCompletion.objects.filter(resolved=True).exists()
    assert not StaleCompletion.objects.filter(resolved=False).exists()
    for user in user_objs:
        StaleCompletion.objects.create(username=user.username, course_key=course_key, block_key=None, force=False)
    perform_cleanup()
    assert not StaleCompletion.objects.filter(resolved=True).exists()
    assert StaleCompletion.objects.filter(resolved=False).exists()
