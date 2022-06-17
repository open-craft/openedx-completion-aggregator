"""
Testing the functionality of asynchronous tasks
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from collections import namedtuple
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
from completion_aggregator.core import OLD_DATETIME, AggregationUpdater
from completion_aggregator.models import Aggregator, StaleCompletion
from completion_aggregator.tasks import aggregation_tasks
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
        super().setUp()
        self.agg_modified = now() - timedelta(days=1)
        course_key = CourseKey.from_string('course-v1:edx+course+test')
        stubcompat = StubCompat([
            course_key.make_usage_key('course', 'course'),
            course_key.make_usage_key('html', 'course-html0'),
            course_key.make_usage_key('html', 'course-html1'),
            course_key.make_usage_key('html', 'course-html2'),
            course_key.make_usage_key('html', 'course-html3'),
            course_key.make_usage_key('other', 'course-other'),
            course_key.make_usage_key('hidden', 'course-hidden0'),
            course_key.make_usage_key('html', 'course-other-html4'),
            course_key.make_usage_key('hidden', 'course-other-hidden1'),
        ])
        for compat_module in 'completion_aggregator.core.compat', 'completion_aggregator.core.compat':
            patch = mock.patch(compat_module, stubcompat)
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
            context_key=self.course_key,
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
            aggregation_tasks.update_aggregators(username='saskia', course_key='course-v1:edx+course+test')
        self.agg.refresh_from_db()
        assert self.agg.last_modified > self.agg_modified
        assert self.agg.earned == 1.0
        assert self.agg.possible == 5.0

    def test_task_with_unknown_user(self):
        StaleCompletion.objects.create(username='unknown', course_key='course-v1:edx+course+test', resolved=False)
        with mock.patch('completion_aggregator.core.update_aggregators') as mock_update_handler:
            aggregation_tasks.update_aggregators(username='unknown', course_key='course-v1:edx+course+test')
        assert StaleCompletion.objects.get(username='unknown').resolved
        mock_update_handler.assert_not_called()

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
                aggregation_tasks.update_aggregators(
                    username='saskia',
                    course_key='course-v1:OpenCraft+Onboarding+2018'
                )
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
                aggregation_tasks.update_aggregators(
                    username='saskia',
                    course_key='course-v1:OpenCraft+Onboarding+2018'
                )


class CalculateUpdatedAggregatorsTestCase(TestCase):
    """
    Test that AggragationUpdater.calculate_updated_aggregators() finds the latest completions.
    """
    expected_result = namedtuple('expected_result', ['block_key', 'earned', 'updated_earned', 'possible'])

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create(username='testuser', email='testuser@example.com')
        self.course_key = CourseKey.from_string('OpenCraft/Onboarding/2018')
        self.blocks = [
            self.course_key.make_usage_key('course', 'course'),
            self.course_key.make_usage_key('chapter', 'course-chapter1'),
            self.course_key.make_usage_key('chapter', 'course-chapter2'),
            self.course_key.make_usage_key('html', 'course-chapter1-block1'),
            self.course_key.make_usage_key('html', 'course-chapter1-block2'),
            self.course_key.make_usage_key('html', 'course-chapter2-block1'),
            self.course_key.make_usage_key('html', 'course-chapter2-block2'),
            # image_explorer is an unregistered block type, and should be
            # treated as EXCLUDED from aggregation.
            self.course_key.make_usage_key('image_explorer', 'course-chapter2-badblock'),
            self.course_key.make_usage_key('chapter', 'course-zeropossible'),
        ]
        patch = mock.patch('completion_aggregator.core.compat', StubCompat(self.blocks))
        patch.start()
        self.addCleanup(patch.stop)

        BlockCompletion.objects.create(
            user=self.user,
            context_key=self.course_key,
            block_key=self.blocks[3],
            completion=1.0,
            modified=now(),
        )

    def _get_updater(self):
        """
        Return a fresh instance of an AggregationUpdater.
        """
        return AggregationUpdater(self.user, self.course_key, mock.MagicMock())

    def assert_expected_results(self, updated, expected):
        """
        Assert that the specified completion values are actually present in
        the database
        """
        updated_dict = {agg.block_key: agg for agg in updated}
        for outcome in expected:
            if outcome.earned is None:
                with self.assertRaises(Aggregator.DoesNotExist):
                    Aggregator.objects.get(block_key=outcome.block_key)
            else:
                agg = Aggregator.objects.get(block_key=outcome.block_key)
                assert agg.earned == outcome.earned
                assert agg.possible == outcome.possible
                assert agg.percent == outcome.earned / outcome.possible
            updated_agg = updated_dict[outcome.block_key]
            assert updated_agg.earned == outcome.updated_earned
            assert updated_agg.possible == outcome.possible
            assert updated_agg.percent == outcome.updated_earned / outcome.possible

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_unmodified_course(self):
        self._get_updater().update()
        self.assert_expected_results(
            self._get_updater().calculate_updated_aggregators(),
            [
                self.expected_result(
                    block_key=self.blocks[0],
                    earned=1.0,
                    updated_earned=1.0,
                    possible=4.0,
                ),
                self.expected_result(
                    block_key=self.blocks[1],
                    earned=1.0,
                    updated_earned=1.0,
                    possible=2.0,
                ),
                self.expected_result(
                    block_key=self.blocks[2],
                    earned=0.0,
                    updated_earned=0.0,
                    possible=2.0,
                ),
            ]
        )

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_modified_course(self):
        self._get_updater().update()
        for block in self.blocks[4], self.blocks[6]:
            BlockCompletion.objects.create(
                user=self.user,
                context_key=self.course_key,
                block_key=block,
                completion=1.0,
                modified=now(),
            )
        self.assert_expected_results(
            self._get_updater().calculate_updated_aggregators(),
            [
                self.expected_result(
                    block_key=self.blocks[0],
                    earned=1.0,
                    updated_earned=3.0,
                    possible=4.0,
                ),
                self.expected_result(
                    block_key=self.blocks[1],
                    earned=1.0,
                    updated_earned=2.0,
                    possible=2.0,
                ),
                self.expected_result(
                    block_key=self.blocks[2],
                    earned=0.0,
                    updated_earned=1.0,
                    possible=2.0,
                ),
            ]
        )

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_pass_changed_blocks_argument(self):
        self._get_updater().update()
        for block in self.blocks[4], self.blocks[6]:
            BlockCompletion.objects.create(
                user=self.user,
                context_key=self.course_key,
                block_key=block,
                completion=1.0,
                modified=now(),
            )
        self.assert_expected_results(
            self._get_updater().calculate_updated_aggregators(changed_blocks={self.blocks[4]}),
            [
                self.expected_result(
                    block_key=self.blocks[0],
                    earned=1.0,
                    updated_earned=3.0,
                    possible=4.0,
                ),
                self.expected_result(
                    block_key=self.blocks[1],
                    earned=1.0,
                    updated_earned=2.0,
                    possible=2.0,
                ),
                self.expected_result(
                    block_key=self.blocks[2],
                    earned=0.0,
                    updated_earned=1.0,  # This was not changed, because block[6] was not marked changed.
                    possible=2.0,
                ),
            ]
        )

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_unknown_block(self):
        self._get_updater().update()
        for block in self.blocks[4], self.blocks[6]:
            BlockCompletion.objects.create(
                user=self.user,
                context_key=self.course_key,
                block_key=block,
                completion=1.0,
                modified=now(),
            )

        unknown_block = self.course_key.make_usage_key('html', 'old-version')
        BlockCompletion.objects.create(
            user=self.user,
            context_key=self.course_key,
            block_key=unknown_block,
            completion=1.0,
            modified=now(),
        )
        self.assert_expected_results(
            self._get_updater().calculate_updated_aggregators(
                changed_blocks={self.blocks[4], unknown_block}
            ),
            [
                self.expected_result(
                    block_key=self.blocks[0],
                    earned=1.0,
                    updated_earned=3.0,
                    possible=4.0,
                ),
                self.expected_result(
                    block_key=self.blocks[1],
                    earned=1.0,
                    updated_earned=2.0,
                    possible=2.0,
                ),
                self.expected_result(
                    block_key=self.blocks[2],
                    earned=0.0,
                    updated_earned=1.0,
                    possible=2.0,
                ),
            ]
        )

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_never_aggregated(self):
        self.assert_expected_results(
            self._get_updater().calculate_updated_aggregators(),
            [
                self.expected_result(
                    block_key=self.blocks[0],
                    earned=None,
                    updated_earned=1.0,
                    possible=4.0,
                ),
                self.expected_result(
                    block_key=self.blocks[1],
                    earned=None,
                    updated_earned=1.0,
                    possible=2.0,
                ),
                self.expected_result(
                    block_key=self.blocks[2],
                    earned=None,
                    updated_earned=0.0,
                    possible=2.0,
                ),
            ]
        )

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_blockstructure_caching(self):
        mock_modulestore = mock.MagicMock()
        updater = AggregationUpdater(self.user, self.course_key, mock_modulestore)
        updater.calculate_updated_aggregators()
        mock_modulestore.bulk_operations.assert_called_once()
        mock_modulestore.bulk_operations.reset_mock()
        updater.calculate_updated_aggregators()
        mock_modulestore.bulk_operations.assert_not_called()


class PartialUpdateTest(TestCase):
    """
    Test that when performing an update for a particular block or subset of
    blocks, that only part of the course tree gets aggregated.
    """
    def setUp(self):
        super().setUp()
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
        patch = mock.patch('completion_aggregator.core.compat', StubCompat(self.blocks))
        patch.start()
        self.addCleanup(patch.stop)

    @XBlock.register_temp_plugin(CourseBlock, 'course')
    @XBlock.register_temp_plugin(OtherAggBlock, 'chapter')
    @XBlock.register_temp_plugin(HTMLBlock, 'html')
    def test_partial_updates(self):
        instant = now()
        completion = BlockCompletion.objects.create(
            user=self.user,
            context_key=self.course_key,
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
            context_key=self.course_key,
            block_key=self.blocks[4],
            completion=0.75,
        )
        # pylint: disable=pointless-string-statement
        '''
            Queries are for the following table
            * Select
                - auth_user (fetch user details)
                - completion_aggregator_aggregator (user specific for specific course)
                - completion_blockcompletion (user specific)
            * Insert or Update Query
                - completion_aggregator_aggregator (insert aggregation data)
            * Update query
                - completion_aggregator_stalecompletion (user specific)
        '''

        with self.assertNumQueries(5):
            aggregation_tasks.update_aggregators(self.user.username, six.text_type(self.course_key), {
                six.text_type(completion.block_key)})

        new_completions = [
            BlockCompletion.objects.create(
                user=self.user,
                context_key=self.course_key,
                block_key=self.blocks[5],
                completion=1.0,
            ),
            BlockCompletion.objects.create(
                user=self.user,
                context_key=self.course_key,
                block_key=self.blocks[6],
                completion=0.5,
            ),
        ]

        with self.assertNumQueries(5):
            aggregation_tasks.update_aggregators(
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


class TaskArgumentHandlingTestCase(TestCase):
    """
    Celery tasks must be called with primitive python types.

    Verify that they are properly parsed before calling into the function that
    does the real work.
    """

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create(username='sandystudent')
        self.course_key = CourseKey.from_string('course-v1:OpenCraft+Onboarding+2018')
        self.block_keys = {
            self.course_key.make_usage_key('html', 'course-chapter-html0'),
            self.course_key.make_usage_key('html', 'course-chapter-html1'),
        }

    @mock.patch('completion_aggregator.core.update_aggregators')
    def test_calling_task_with_no_blocks(self, mock_update):
        with self.assertNumQueries(1):
            aggregation_tasks.update_aggregators(
                username='sandystudent',
                course_key='course-v1:OpenCraft+Onboarding+2018'
            )
        mock_update.assert_called_once_with(
            self.user, self.course_key, frozenset(), False
        )

    @mock.patch('completion_aggregator.core.update_aggregators')
    def test_calling_task_with_changed_blocks(self, mock_update):
        with self.assertNumQueries(1):
            aggregation_tasks.update_aggregators(
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
