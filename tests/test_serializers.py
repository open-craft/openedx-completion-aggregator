"""
Test serialization of completion data.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import ddt
from mock import patch
from opaque_keys.edx.keys import CourseKey
from xblock.core import XBlock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from completion_aggregator import models
from completion_aggregator.serializers import (AggregationUpdater, AggregatorAdapter,
                                               course_completion_serializer_factory)
from test_utils.compat import StubCompat
from test_utils.test_blocks import StubCourse, StubSequential

empty_compat = StubCompat([])


class AggregatorAdapterTestCase(TestCase):
    """
    Test the behavior of the AggregatorAdapter
    """
    def setUp(self):
        super(AggregatorAdapterTestCase, self).setUp()
        self.test_user = User.objects.create()
        self.course_key = CourseKey.from_string("course-v1:z+b+c")

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    def test_simple_aggregation_structure(self):
        course_completion, _ = models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='course', block_id='course'),
            aggregation_name='course',
            earned=4.2,
            possible=9.6,
            last_modified=timezone.now(),
        )
        sequential_completion, _ = models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='sequential', block_id='chap1'),
            aggregation_name='sequential',
            earned=1.8,
            possible=3.4,
            last_modified=timezone.now(),
        )
        agstruct = AggregatorAdapter(
            user=self.test_user,
            course_key=self.course_key,
        )
        agstruct.add_aggregator(course_completion)
        agstruct.update_aggregators([sequential_completion])

        self.assertEqual(agstruct.course, course_completion)
        self.assertEqual(agstruct.sequential, [sequential_completion])


@ddt.ddt
@patch('completion_aggregator.serializers.compat', empty_compat)
@patch('completion_aggregator.tasks.aggregation_tasks.compat', empty_compat)
class CourseCompletionSerializerTestCase(TestCase):
    """
    Test that the CourseCompletionSerializer returns appropriate results.
    """

    def setUp(self):
        super(CourseCompletionSerializerTestCase, self).setUp()
        self.test_user = User.objects.create()
        self.course_key = CourseKey.from_string('course-v1:abc+def+ghi')

    def assert_serialized_completions(self, serializer_cls_args, extra_body):
        """
        Ensures that the course completion serializer returns the expected results
        for this set of submitted completions.
        """
        serializer_cls = course_completion_serializer_factory(serializer_cls_args)
        completions = [
            models.Aggregator.objects.submit_completion(
                user=self.test_user,
                course_key=self.course_key,
                aggregation_name='course',
                block_key=self.course_key.make_usage_key(block_type='course', block_id='course'),
                earned=16.0,
                possible=19.0,
                last_modified=timezone.now(),
            )[0],
            models.Aggregator.objects.submit_completion(
                user=self.test_user,
                course_key=self.course_key,
                aggregation_name='sequential',
                block_key=self.course_key.make_usage_key(block_type='sequential', block_id='seq1'),
                earned=6.0,
                possible=7.0,
                last_modified=timezone.now(),
            )[0],
            models.Aggregator.objects.submit_completion(
                user=self.test_user,
                course_key=self.course_key,
                aggregation_name='sequential',
                block_key=self.course_key.make_usage_key(block_type='sequential', block_id='seq2'),
                earned=10.0,
                possible=12.0,
                last_modified=timezone.now(),
            )[0],
        ]
        completion = AggregatorAdapter(
            user=self.test_user,
            course_key=self.course_key,
            queryset=completions,
        )
        serial = serializer_cls(completion)
        expected = {
            'course_key': str(self.course_key),
            'completion': {
                'earned': 16.0,
                'possible': 19.0,
                'percent': 16 / 19,
            },
        }
        expected.update(extra_body)
        self.assertEqual(
            serial.data,
            expected,
        )

    @ddt.data(
        [[], {}],
        [
            ['sequential'],
            {
                'sequential': [
                    {
                        'course_key': 'course-v1:abc+def+ghi',
                        'block_key': 'block-v1:abc+def+ghi+type@sequential+block@seq1',
                        'completion': {'earned': 6.0, 'possible': 7.0, 'percent': 6 / 7},
                    },
                    {
                        'course_key': 'course-v1:abc+def+ghi',
                        'block_key': 'block-v1:abc+def+ghi+type@sequential+block@seq2',
                        'completion': {'earned': 10.0, 'possible': 12.0, 'percent': 5 / 6},
                    },
                ]
            }
        ]
    )
    @ddt.unpack
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @patch.object(AggregationUpdater, 'update')
    def test_serialize_student_progress_object(self, serializer_cls_args, extra_body, mock_update):
        self.assert_serialized_completions(serializer_cls_args, extra_body)
        # no stale completions, so aggregations were not updated
        assert mock_update.call_count == 0

    @ddt.data(
        None,
        'block-v1:abc+def+ghi+type@course+block@course',
        'block-v1:abc+def+ghi+type@sequential+block@seq1',
        'block-v1:abc+def+ghi+type@sequential+block@seq2'
    )
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @patch.object(AggregationUpdater, 'update')
    def test_aggregation_with_stale_completions(self, stale_block_key, mock_update):
        # Mark a completion as stale for the given block key
        models.StaleCompletion.objects.create(
            username=self.test_user.username,
            course_key=self.course_key,
            block_key=stale_block_key,
            force=True,
        )
        self.assert_serialized_completions([], {})
        # Ensure the aggregations were recalculated due to the stale completion
        assert mock_update.call_count == 1

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_zero_possible(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        completion, _ = models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=course_key,
            block_key=course_key.make_usage_key(block_type='course', block_id='course'),
            aggregation_name='course',
            earned=0.0,
            possible=0.0,
            last_modified=timezone.now(),
        )
        serial = course_completion_serializer_factory([])(AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            queryset=[completion]
        ))
        self.assertEqual(
            serial.data['completion'],
            {
                'earned': 0.0,
                'possible': 0.0,
                'percent': 1.0,
            },
        )

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_invalid_aggregator(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        completion, _ = models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=course_key,
            block_key=course_key.make_usage_key(block_type='course', block_id='course'),
            aggregation_name='course',
            earned=0.0,
            possible=0.0,
            last_modified=timezone.now(),
        )
        agg = AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            queryset=[completion]
        )
        # coverage demands this, because we have __getattr__ overridden
        with self.assertRaises(AttributeError):
            agg.something_that_doesnt_exist  # pylint: disable=pointless-statement

    def test_aggregation_without_completions(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        serial = course_completion_serializer_factory([])(AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            queryset=[]
        ))
        self.assertEqual(
            serial.data['completion'],
            {
                'earned': 0.0,
                'possible': None,
                'percent': None,
            },
        )

    def test_filtering_completions(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        other_course_key = CourseKey.from_string('course-v1:ihg+fed+cba')
        other_user = User.objects.create(username='other')
        agg = AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            queryset=[
                models.Aggregator.objects.submit_completion(
                    user=other_user,
                    course_key=course_key,
                    block_key=course_key.make_usage_key(block_type='course', block_id='course'),
                    aggregation_name='course',
                    earned=4.0,
                    possible=4.0,
                    last_modified=timezone.now(),
                )[0],
                models.Aggregator.objects.submit_completion(
                    user=self.test_user,
                    course_key=other_course_key,
                    block_key=other_course_key.make_usage_key(block_type='course', block_id='course'),
                    aggregation_name='course',
                    earned=1.0,
                    possible=3.0,
                    last_modified=timezone.now(),
                )[0],
                models.Aggregator.objects.submit_completion(
                    user=self.test_user,
                    course_key=course_key,
                    block_key=course_key.make_usage_key(block_type='video', block_id='neatvideo'),
                    aggregation_name='video',
                    earned=1.0,
                    possible=2.0,
                    last_modified=timezone.now(),
                )[0]
            ]
        )
        self.assertEqual(len(agg.aggregators), 0)
