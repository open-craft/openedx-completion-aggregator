"""
Testing the functionality of asynchronous tasks
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta

import ddt
import mock
import pytest
import six
from opaque_keys.edx.keys import CourseKey
from xblock.core import XBlock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from completion.models import BlockCompletion
from completion_aggregator.models import Aggregator
from completion_aggregator.tasks.aggregation_tasks import OLD_DATETIME, AggregationUpdater, update_aggregators
from test_utils.compat import StubCompat
from test_utils.xblocks import CourseBlock, HiddenBlock, HTMLBlock, InvalidModeBlock, OtherAggBlock


@ddt.ddt
class AggregationUpdaterTestCase(TestCase):
    """
    Test the AggregationUpdater.

    It should create Aggregator records for new completion objects.
    """
    def setUp(self):
        """
        For the purpose of the tests, we will use the following course
        structure:

                        course
                          |
                +--+---+--^-+----+----+
               /   |   |    |    |     \\
            html html html html other hidden
                                /   \\
                              html hidden

        where `course` and `other` are a completion_mode of AGGREGATOR (but
        only `course` is registered to store aggregations), `html` is
        COMPLETABLE, and `hidden` is EXCLUDED.
        """
        self.agg_modified = now() - timedelta(days=1)
        course_key = CourseKey.from_string('course-v1:edx+course+test')
        patch = mock.patch('completion_aggregator.tasks.aggregation_tasks.compat', StubCompat([
            course_key.make_usage_key('course', 'course'),
            course_key.make_usage_key('html', 'course-html0'),
            course_key.make_usage_key('html', 'course-html1'),
            course_key.make_usage_key('html', 'course-html2'),
            course_key.make_usage_key('html', 'course-html3'),
            course_key.make_usage_key('other', 'course-other'),
            course_key.make_usage_key('hidden', 'course-hidden0'),
            course_key.make_usage_key('html', 'course-other-html4'),
            course_key.make_usage_key('hidden', 'course-other-hidden1'),
        ]))
        patch.start()
        self.addCleanup(patch.stop)
        user = get_user_model().objects.create(username='saskia')
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
            block_key=self.course_key.make_usage_key('html', 'course-other-html4'),
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
    def test_end_to_end_task_calling(self):
        '''
            Queries are for the following table
            * Select
                - auth_user (fetch user details)
                - completion_aggregator_aggregator (user specific for specific course)
                - completion_blockcompletion (user specific)
                - auth user (fetch user details)
            * Insert or Update Query
                - completion_aggregator_aggregator (insert aggregation data)
            * Update query
                - completion_aggregator_stalecompletion (user specific)
        '''
        with self.assertNumQueries(6):
            update_aggregators(username='saskia', course_key='course-v1:edx+course+test')
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

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(InvalidModeBlock, 'html')
    @XBlock.register_temp_plugin(HiddenBlock, 'hidden')
    @XBlock.register_temp_plugin(OtherAggBlock, 'other')
    def test_invalid_completion_mode(self):
        with pytest.raises(ValueError):
            self.updater.update()

    @ddt.data(ValueError, TypeError)
    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(InvalidModeBlock, 'html')
    @XBlock.register_temp_plugin(HiddenBlock, 'hidden')
    @XBlock.register_temp_plugin(OtherAggBlock, 'other')
    def test_expected_updater_errors(self, exception_class):
        # Verify that no exception is bubbled up when the constructor errors, but that the update method is not called.
        with mock.patch.object(AggregationUpdater, '__init__') as mock_update_constructor:
            mock_update_constructor.side_effect = exception_class('test')
            with mock.patch.object(AggregationUpdater, 'update') as mock_update_action:
                update_aggregators(username='saskia', course_key='course-v1:OpenCraft+Onboarding+2018')
                assert not mock_update_action.called

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(InvalidModeBlock, 'html')
    @XBlock.register_temp_plugin(HiddenBlock, 'hidden')
    @XBlock.register_temp_plugin(OtherAggBlock, 'other')
    def test_unexpected_updater_errors(self):
        # Verify that no exception is bubbled up when the constructor errors, but that the update method is not called.
        with mock.patch.object(AggregationUpdater, '__init__') as mock_update_constructor:
            mock_update_constructor.side_effect = RuntimeError('test')
            with pytest.raises(RuntimeError):
                update_aggregators(username='saskia', course_key='course-v1:OpenCraft+Onboarding+2018')


class PartialUpdateTest(TestCase):
    """
    Test that when performing an update for a particular block or subset of
    blocks, that only part of the course tree gets aggregated.
    """
    def setUp(self):
        self.user = get_user_model().objects.create()
        self.course_key = CourseKey.from_string('OpenCraft/Onboarding/2018')
        self.blocks = [
            self.course_key.make_usage_key('course', 'course'),
            self.course_key.make_usage_key('chapter', 'course-chapter1'),
            self.course_key.make_usage_key('chapter', 'course-chapter2'),
            self.course_key.make_usage_key('html', 'course-chapter1-block1'),
            self.course_key.make_usage_key('html', 'course-chapter1-block2'),
            self.course_key.make_usage_key('html', 'course-chapter2-block1'),
            self.course_key.make_usage_key('html', 'course-chapter2-block2'),
        ]
        patch = mock.patch('completion_aggregator.tasks.aggregation_tasks.compat', StubCompat(self.blocks))
        patch.start()
        self.addCleanup(patch.stop)

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_partial_updates(self):
        instant = now()
        completion = BlockCompletion.objects.create(
            user=self.user,
            course_key=self.course_key,
            block_key=self.blocks[4],
            completion=0.75,
            modified=instant,
        )

        updater = AggregationUpdater(self.user, self.course_key, mock.MagicMock())
        updater.update(changed_blocks={self.blocks[4]})
        course_agg = Aggregator.objects.get(course_key=self.course_key, block_key=self.blocks[0])
        chap1_agg = Aggregator.objects.get(course_key=self.course_key, block_key=self.blocks[1])
        chap2_agg = Aggregator.objects.get(course_key=self.course_key, block_key=self.blocks[2])
        self.assertEqual(chap1_agg.earned, 0.75)
        self.assertEqual(chap1_agg.last_modified, completion.modified)
        self.assertEqual(chap2_agg.earned, 0.0)
        self.assertEqual(chap2_agg.last_modified, OLD_DATETIME)
        self.assertEqual(course_agg.earned, 0.75)
        self.assertEqual(course_agg.last_modified, completion.modified)

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_multiple_partial_updates(self):
        completion = BlockCompletion.objects.create(
            user=self.user,
            course_key=self.course_key,
            block_key=self.blocks[4],
            completion=0.75,
        )
        '''
            Queries are for the following table
            * Select
                - auth_user (fetch user details)
                - completion_aggregator_aggregator (user specific for specific course)
                - completion_blockcompletion (user specific)
                - completion_aggregator_aggregator (user specific for specific course and block)
            * Insert or Update Query
                - completion_aggregator_aggregator (insert aggregation data)
            * Update query
                - completion_aggregator_stalecompletion (user specific)
        '''   # pylint: disable=pointless-string-statement

        with self.assertNumQueries(6):
            update_aggregators(self.user.username, six.text_type(self.course_key), {
                six.text_type(completion.block_key)})

        new_completions = [
            BlockCompletion.objects.create(
                user=self.user,
                course_key=self.course_key,
                block_key=self.blocks[5],
                completion=1.0,
            ),
            BlockCompletion.objects.create(
                user=self.user,
                course_key=self.course_key,
                block_key=self.blocks[6],
                completion=0.5,
            ),
        ]

        with self.assertNumQueries(6):
            update_aggregators(
                username=self.user.username,
                course_key=six.text_type(self.course_key),
                block_keys=[six.text_type(comp.block_key) for comp in new_completions]
            )

        course_agg = Aggregator.objects.get(course_key=self.course_key, block_key=self.blocks[0])
        chap1_agg = Aggregator.objects.get(course_key=self.course_key, block_key=self.blocks[1])
        chap2_agg = Aggregator.objects.get(course_key=self.course_key, block_key=self.blocks[2])
        self.assertEqual(chap1_agg.earned, 0.75)
        self.assertEqual(chap1_agg.last_modified, completion.modified)
        self.assertEqual(chap2_agg.earned, 1.5)
        self.assertEqual(chap2_agg.last_modified, new_completions[1].modified)
        self.assertEqual(course_agg.earned, 2.25)
        self.assertEqual(course_agg.last_modified, new_completions[1].modified)


class TaskArgumentHandling(TestCase):
    """
    Celery tasks must be called with primitive python types.

    Verify that they are properly parsed before calling into the function that
    does the real work.
    """

    def setUp(self):
        self.user = get_user_model().objects.create(username='sandystudent')
        self.course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
        self.block_keys = {
            self.course_key.make_usage_key('html', 'course-chapter-html0'),
            self.course_key.make_usage_key('html', 'course-chapter-html1'),
        }

    @mock.patch('completion_aggregator.tasks.aggregation_tasks._update_aggregators')
    def test_calling_task_with_no_blocks(self, mock_update):
        with self.assertNumQueries(1):
            update_aggregators(username='sandystudent', course_key='course-v1:OpenCraft+Onboarding+2018')
        mock_update.assert_called_once_with(
            self.user, self.course_key, frozenset(), False
        )

    @mock.patch('completion_aggregator.tasks.aggregation_tasks._update_aggregators')
    def test_calling_task_with_changed_blocks(self, mock_update):
        with self.assertNumQueries(1):
            update_aggregators(
                username='sandystudent',
                course_key='course-v1:OpenCraft+Onboarding+2018',
                block_keys=[
                    'block-v1:OpenCraft+Onboarding+2018+type@html+block@course-chapter-html0',
                    'block-v1:OpenCraft+Onboarding+2018+type@html+block@course-chapter-html1',
                ],
            )
        mock_update.assert_called_once_with(
            self.user,
            self.course_key,
            self.block_keys,
            False,
        )

    def test_unknown_username(self):
        with pytest.raises(get_user_model().DoesNotExist):
            with self.assertNumQueries(0):
                update_aggregators(username='sanfordstudent', course_key='course-v1:OpenCraft+Onboarding+2018')
