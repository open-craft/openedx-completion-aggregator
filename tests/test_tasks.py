"""
Testing the functionality of asynchronous tasks
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta

import mock
from opaque_keys.edx.keys import CourseKey
from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from completion.models import BlockCompletion
from completion_aggregator.models import Aggregator
from completion_aggregator.tasks import AggregationUpdater
from test_utils.compat import StubCompat


class CourseBlock(XBlock):
    """
    A registered aggregator block.
    """
    completion_mode = XBlockCompletionMode.AGGREGATOR


class HTMLBlock(XBlock):
    """
    A completable block.
    """
    completion_mode = XBlockCompletionMode.COMPLETABLE


class HiddenBlock(XBlock):
    """
    An excluded block.
    """
    completion_mode = XBlockCompletionMode.EXCLUDED


class OtherAggBlock(XBlock):
    """
    An unregistered aggregator block.
    """
    completion_mode = XBlockCompletionMode.AGGREGATOR


class AggregationUpdaterTestCase(TestCase):
    """
    Test the AggregationUpdater.

    It should create Aggregator records for new completion objects.
    """
    def setUp(self):
        self.agg_modified = now() - timedelta(days=1)
        patch = mock.patch('completion_aggregator.tasks.compat', StubCompat())
        patch.start()
        self.addCleanup(patch.stop)
        user = get_user_model().objects.create()
        self.course_key = CourseKey.from_string('course-v1:edx+course+test')
        self.agg, _ = Aggregator.objects.submit_completion(
            user=user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key('course', 'course'),
            aggregation_name='course',
            earned=0.0,
            possible=0.0,
            last_modified=self.agg_modified,
        )
        BlockCompletion.objects.create(
            user=user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key('html', 'html4'),
            completion=1.0,
            modified=now(),
        )
        self.updater = AggregationUpdater(user, self.course_key, mock.MagicMock())

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    @XBlock.register_temp_plugin(HiddenBlock, 'hidden')
    @XBlock.register_temp_plugin(OtherAggBlock, 'other')
    def test_aggregation_update(self):
        self.updater.update()
        self.agg.refresh_from_db()
        assert self.agg.last_modified > self.agg_modified
        assert self.agg.earned == 1.0
        assert self.agg.possible == 5.0

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    @XBlock.register_temp_plugin(HiddenBlock, 'hidden')
    @XBlock.register_temp_plugin(OtherAggBlock, 'other')
    def test_unregistered_not_recorded(self):
        self.updater.update()
        assert not any(agg.block_key.block_type == 'other' for agg in Aggregator.objects.all())

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    @XBlock.register_temp_plugin(HiddenBlock, 'hidden')
    @XBlock.register_temp_plugin(OtherAggBlock, 'other')
    def test_with_no_initial_aggregator(self):
        self.agg.delete()
        self.updater.update()
        aggs = Aggregator.objects.filter(course_key=self.course_key)
        assert len(aggs) == 1
        agg = aggs[0]
        assert agg.course_key == self.course_key
        assert agg.aggregation_name == 'course'
        assert agg.earned == 1.0
        assert agg.possible == 5.0
