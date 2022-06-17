# -*- coding: utf-8 -*-

"""
Tests for the `openedx-completion-aggregator` models module.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import ddt
import pytest
import six
from opaque_keys.edx.keys import UsageKey

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.timezone import now

from completion_aggregator.models import Aggregator


@ddt.ddt
class AggregatorTestCase(TestCase):
    """
    Tests of the Aggregator model
    """
    BLOCK_KEY = 'block-v1:edx+test+run+type@video+block@doggos'
    BLOCK_KEY_OBJ = UsageKey.from_string(BLOCK_KEY)
    COURSE_KEY_OBJ = UsageKey.from_string(BLOCK_KEY).course_key

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create(username='testuser')

    def test_submit_completion_with_invalid_user(self):
        with pytest.raises(TypeError):
            Aggregator.objects.submit_completion(
                user="I am a user",
                course_key=self.BLOCK_KEY_OBJ.course_key,
                block_key=self.BLOCK_KEY_OBJ,
                aggregation_name='chapter',
                earned=24.0,
                possible=27.0,
                last_modified=now(),
            )

    @ddt.data(
        # Valid arguments
        (BLOCK_KEY_OBJ, 'course', 0.5, 1, 0.5),
    )
    @ddt.unpack
    def test_submit_completion_with_valid_data(self, block_key_obj, aggregate_name, earned, possible, expected_percent):
        obj, is_new = Aggregator.objects.submit_completion(
            user=self.user,
            course_key=block_key_obj.course_key,
            block_key=block_key_obj,
            aggregation_name=aggregate_name,
            earned=earned,
            possible=possible,
            last_modified=now(),
        )
        self.assertTrue(is_new)
        self.assertEqual(len(Aggregator.objects.all()), 1)
        self.assertEqual(obj.earned, earned)
        self.assertEqual(obj.possible, possible)
        self.assertEqual(obj.percent, expected_percent)

    @ddt.data(
        # Earned greater than possible
        (BLOCK_KEY_OBJ, COURSE_KEY_OBJ, 'course', 1.1, 1,
         ValueError, "The earned cannot be larger than the possible value."),
        # Earned is less than zero.
        (BLOCK_KEY_OBJ, COURSE_KEY_OBJ, 'course', -0.5, 1,
         ValidationError, "{'percent': [u'-0.5 must be between 0.0 and 1.0'],"
                          " 'earned': [u'-0.5 must be larger than 0.']}"),
        # Possible is less than zero.
        (BLOCK_KEY_OBJ, COURSE_KEY_OBJ, 'course', -1.5, -1,
         ValidationError, "{'percent': [u'1.5 must be between 0.0 and 1.0'],"
                          " 'possible': [u'-1.0 must be larger than 0.'],"
                          " 'earned': [u'-1.5 must be larger than 0.']}"),
        # TypeError for Block Key
        (BLOCK_KEY, COURSE_KEY_OBJ, 'course', 0.5, 1,
         TypeError, "{'percent': [u'1.5 must be between 0.0 and 1.0'],"
                    " 'possible': [u'-1.0 must be larger than 0.'],"
                    " 'earned': [u'-1.5 must be larger than 0.']}"),
        # TypeError for Course Key
        (BLOCK_KEY_OBJ, str(COURSE_KEY_OBJ), 'course', 0.5, 1,
         TypeError, "{'percent': [u'1.5 must be between 0.0 and 1.0'],"
                    " 'possible': [u'-1.0 must be larger than 0.'],"
                    " 'earned': [u'-1.5 must be larger than 0.']}"),
    )
    @ddt.unpack
    def test_submit_completion_with_exception(
            self, block_key, course_key, aggregate_name, earned, possible, exception_type, exception_message
    ):
        with self.assertRaises(exception_type) as context_manager:
            Aggregator.objects.submit_completion(
                user=self.user,
                course_key=course_key,
                block_key=block_key,
                aggregation_name=aggregate_name,
                earned=earned,
                possible=possible,
                last_modified=now()
            )

            self.assertEqual(exception_message, str(context_manager.exception))

    @ddt.data(
        (
            BLOCK_KEY_OBJ, 'course', 0.5, 1, 0.5,
        )
    )
    @ddt.unpack
    def test_aggregate_completion_string(
            self, block_key_obj, aggregate_name, earned, possible, expected_percent
    ):
        obj, _is_new = Aggregator.objects.submit_completion(
            user=self.user,
            course_key=block_key_obj.course_key,
            block_key=block_key_obj,
            aggregation_name=aggregate_name,
            earned=earned,
            possible=possible,
            last_modified=now(),
        )
        expected_string = (
            f'Aggregator: {self.user.username}, {six.text_type(block_key_obj.course_key)}, '
            f'{six.text_type(block_key_obj)}: {expected_percent}'
        )
        self.assertEqual(six.text_type(obj), expected_string)

    @ddt.data(
        # Changes the value of earned. This does not create a new object.
        (
            BLOCK_KEY_OBJ, 'course', 0.5, 1, 0.5,
            BLOCK_KEY_OBJ, 'course', 0.7, 1, 0.7, False
        ),
        # Changes the value of possible. This does not create a new object.
        (
            BLOCK_KEY_OBJ, 'course', 0.5, 1, 0.5,
            BLOCK_KEY_OBJ, 'course', 0.5, 2, 0.25, False
        ),
        # Changes the value of aggregate_name. This creates a new object.
        (
            BLOCK_KEY_OBJ, 'course', 0.5, 1, 0.5,
            BLOCK_KEY_OBJ, 'chapter', 0.5, 1, 0.5, True
        ),
        # Changes the block_key. This creates a new object.
        (
            BLOCK_KEY_OBJ, 'course', 0.5, 1, 0.5,
            UsageKey.from_string('block-v1:edX+DemoX+Demo_Course+type@sequential+block@workflow'),
            'course', 0.5, 1, 0.5, True
        ),
    )
    @ddt.unpack
    def test_submit_completion_twice_with_changes(
            self,
            block_key_obj,
            aggregate_name,
            earned,
            possible,
            expected_percent,
            new_block_key_obj,
            new_aggregate_name,
            new_earned,
            new_possible,
            new_percent,
            is_second_obj_new,
    ):
        obj, is_new = Aggregator.objects.submit_completion(
            user=self.user,
            course_key=block_key_obj.course_key,
            block_key=block_key_obj,
            aggregation_name=aggregate_name,
            earned=earned,
            possible=possible,
            last_modified=now(),
        )
        self.assertEqual(obj.percent, expected_percent)
        self.assertTrue(is_new)

        new_obj, is_new = Aggregator.objects.submit_completion(
            user=self.user,
            course_key=new_block_key_obj.course_key,
            block_key=new_block_key_obj,
            aggregation_name=new_aggregate_name,
            earned=new_earned,
            possible=new_possible,
            last_modified=now(),
        )
        self.assertEqual(new_obj.percent, new_percent)
        self.assertEqual(is_new, is_second_obj_new)
        if is_second_obj_new:
            self.assertNotEqual(obj.id, new_obj.id)

    @ddt.data(
        (BLOCK_KEY_OBJ, 'course', 0.5, 1, 0.5),
    )
    @ddt.unpack
    def test_get_values(self, block_key_obj, aggregate_name, earned, possible, expected_percent):
        aggregator = Aggregator(
            user=self.user,
            course_key=block_key_obj.course_key,
            block_key=block_key_obj,
            aggregation_name=aggregate_name,
            earned=earned,
            possible=possible,
            last_modified=now(),
        )
        values = aggregator.get_values()
        self.assertEqual(values['user'], self.user.id)
        self.assertEqual(values['percent'], expected_percent)
