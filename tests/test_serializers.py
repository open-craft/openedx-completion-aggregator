"""
Test serialization of completion data.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import ddt
import pytest
from mock import patch
from opaque_keys.edx.keys import CourseKey
from xblock.core import XBlock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from completion_aggregator import models, serializers
from completion_aggregator.core import AggregationUpdater
from test_utils.compat import StubCompat
from test_utils.test_blocks import StubCourse, StubSequential

User = get_user_model()

stub_compat = StubCompat([
    CourseKey.from_string('course-v1:abc+def+ghi').make_usage_key('course', 'course'),
])


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
            block_key=self.course_key.make_usage_key(block_type='course', block_id='crs'),
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
        agstruct = serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=self.course_key,
        )
        agstruct.add_aggregator(course_completion)
        agstruct.update_aggregators([sequential_completion])

        self.assertEqual(agstruct.course, course_completion)
        self.assertEqual(agstruct.sequential, [sequential_completion])


def _course_completion_serializer_factory(serializer_cls_args):
    return serializers.course_completion_serializer_factory(
        serializer_cls_args,
        course_completion_serializer=serializers.CourseCompletionSerializer,
        block_completion_serializer=serializers.BlockCompletionSerializer,
    )


@ddt.ddt
@patch('completion_aggregator.serializers.compat', stub_compat)
@patch('completion_aggregator.core.compat', stub_compat)
class CourseCompletionSerializerTestCase(TestCase):
    """
    Test that the CourseCompletionSerializer returns appropriate results.
    """

    def setUp(self):
        super(CourseCompletionSerializerTestCase, self).setUp()
        self.test_user = User.objects.create()
        self.course_key = CourseKey.from_string('course-v1:abc+def+ghi')

    def assert_serialized_completions(self, serializer_cls_args, extra_body, recalc_stale):
        """
        Ensures that the course completion serializer returns the expected results
        for this set of submitted completions.
        """
        serializer_cls = _course_completion_serializer_factory(serializer_cls_args)
        aggregators = [
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
        is_stale = recalc_stale and models.StaleCompletion.objects.filter(
            username=self.test_user.username,
            course_key=self.course_key,
            resolved=False
        )
        completion = serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=self.course_key,
            aggregators=aggregators,
            recalculate_stale=recalc_stale,
        )
        serial = serializer_cls(completion)
        expected = {
            'course_key': str(self.course_key),
            'completion': {
                'earned': 0.0 if is_stale else 16.0,
                'possible': None if is_stale else 19.0,
                'percent': 0.0 if is_stale else 16 / 19,
            },
        }

        expected.update(extra_body)
        # Need to allow for rounding error when retrieving the percent from the test database
        self.assertEqual(serial.data['course_key'], expected['course_key'])
        self.assertEqual(serial.data['completion']['earned'], expected['completion']['earned'])
        self.assertEqual(serial.data['completion']['possible'], expected['completion']['possible'])
        self.assertAlmostEqual(serial.data['completion']['possible'], expected['completion']['possible'], places=14)

    @ddt.data(
        [[], {}, False],
        [[], {}, True],
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
            },
            False
        ],
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
            },
            True
        ]
    )
    @ddt.unpack
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    def test_serialize_aggregators(self, serializer_cls_args, extra_body, recalc_stale):
        assert not models.StaleCompletion.objects.filter(resolved=False).exists()
        self.assert_serialized_completions(serializer_cls_args, extra_body, recalc_stale)

    @ddt.data(
        (None, True, False),
        (None, True, True),
        (None, False, False),
        (None, False, True),
        ('block-v1:abc+def+ghi+type@course+block@course', True, False),
        ('block-v1:abc+def+ghi+type@course+block@course', False, False),
        ('block-v1:abc+def+ghi+type@sequential+block@seq1', True, False),
        ('block-v1:abc+def+ghi+type@sequential+block@seq1', False, False),
        ('block-v1:abc+def+ghi+type@sequential+block@seq2', True, False),
        ('block-v1:abc+def+ghi+type@sequential+block@seq2', False, False),
        ('block-v1:abc+def+ghi+type@course+block@course', True, True),
        ('block-v1:abc+def+ghi+type@course+block@course', False, True),
        ('block-v1:abc+def+ghi+type@sequential+block@seq1', True, True),
        ('block-v1:abc+def+ghi+type@sequential+block@seq1', False, True),
        ('block-v1:abc+def+ghi+type@sequential+block@seq2', True, True),
        ('block-v1:abc+def+ghi+type@sequential+block@seq2', False, True),
    )
    @ddt.unpack
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @patch.object(AggregationUpdater, 'calculate_updated_aggregators')
    def test_aggregation_recalc_stale_completions(self, stale_block_key, stale_force, recalc_stale, mock_calculate):
        """
        Ensure that requesting aggregation when recalculating stale completions
        causes the aggregations to be recalculated once, but does not resolve
        stale completions.
        """
        models.StaleCompletion.objects.create(
            username=self.test_user.username,
            course_key=self.course_key,
            block_key=stale_block_key,
            force=stale_force,
        )
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1
        self.assert_serialized_completions([], {}, recalc_stale)
        if recalc_stale:
            assert mock_calculate.call_count == 1
            assert models.StaleCompletion.objects.filter(resolved=False).count() == 1
        else:
            assert mock_calculate.call_count == 0
            assert models.StaleCompletion.objects.filter(resolved=False).count() == 1

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
        serial = _course_completion_serializer_factory([])(serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            aggregators=[completion]
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
    def test_mean_with_no_completions(self):
        # A course that has no aggregators recorded.
        course_key = CourseKey.from_string('course-v1:abc+def+ghj')
        serial = _course_completion_serializer_factory(['mean'])(serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            aggregators=[],
        ), requested_fields={'mean'})
        self.assertAlmostEqual(serial.data['mean'], 0)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_mean(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        data = [
            # earned, possible
            (5., 20.),
            (7., 14.),
            (3., 9.),
            (8., 14.),
        ]
        expected_mean = sum(item[0] / item[1] for item in data) / 5.
        completions = [
            models.Aggregator.objects.submit_completion(
                user=self.test_user,
                course_key=course_key,
                block_key=course_key.make_usage_key(block_type='course', block_id=f'course{idx}'),
                aggregation_name='course',
                earned=data[idx][0],
                possible=data[idx][1],
                last_modified=timezone.now(),
            )[0]
            for idx in range(4)
        ]
        serial = _course_completion_serializer_factory(['mean'])(serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            aggregators=completions
        ), requested_fields={'mean'})
        self.assertAlmostEqual(serial.data['mean'], expected_mean)

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
        agg = serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            aggregators=[completion]
        )
        # coverage demands this, because we have __getattr__ overridden
        with self.assertRaises(AttributeError):
            agg.something_that_doesnt_exist  # pylint: disable=pointless-statement

    def test_aggregation_without_completions(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        serial = _course_completion_serializer_factory([])(serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            aggregators=[]
        ))
        self.assertEqual(
            serial.data['completion'],
            {
                'earned': 0.0,
                'possible': None,
                'percent': 0.0,
            },
        )

    def test_validating_completions(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        other_course_key = CourseKey.from_string('course-v1:ihg+fed+cba')
        other_user = User.objects.create(username='other')
        aggregators = [
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
        ]
        for agg in aggregators:
            with pytest.raises(ValueError):
                serializers.AggregatorAdapter(
                    user=self.test_user,
                    course_key=course_key,
                    aggregators=[agg],
                )

    def test_filtering_completions(self):
        course_key = CourseKey.from_string('course-v1:abc+def+ghi')
        aggregator = models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=course_key,
            block_key=course_key.make_usage_key(block_type='video', block_id='neatvideo'),
            aggregation_name='video',
            earned=1.0,
            possible=2.0,
            last_modified=timezone.now(),
        )[0]
        adapted = serializers.AggregatorAdapter(
            user=self.test_user,
            course_key=course_key,
            aggregators=[aggregator],
        )
        assert not adapted.aggregators
