# -*- coding: utf-8 -*-

"""
Tests for the `openedx-completion-aggregator` tasks.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import ddt
import mock
from freezegun import freeze_time
from opaque_keys.edx.keys import CourseKey

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings

from completion.models import BlockCompletion
from completion_aggregator.tasks.aggregation_tasks import _migrate_batch
from test_utils.compat import StubCompat
from test_utils.test_app.models import CourseModuleCompletion

User = get_user_model()


@ddt.ddt
@override_settings(
    COMPLETION_AGGREGATOR_AGGREGATION_LOCK='COMPLETION_AGGREGATOR_AGGREGATION_LOCK',
    COMPLETION_AGGREGATOR_CLEANUP_LOCK='COMPLETION_AGGREGATOR_CLEANUP_LOCK',
    COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS=1800,
    COMPLETION_AGGREGATOR_CLEANUP_LOCK_TIMEOUT_SECONDS=900,
)
class MigrateProgressTestCase(TestCase):
    """
    Tests of the progress migration code.
    """

    def setUp(self):
        super(MigrateProgressTestCase, self).setUp()
        self.user = user = User.objects.create_user("test", password="test")
        self.course_key = course_key = CourseKey.from_string('course-v1:edx+course+test')
        self.block_keys = block_keys = [
            course_key.make_usage_key('html', f'course-html{idx}')
            for idx in range(1, 51)
        ]
        stubcompat = StubCompat([course_key.make_usage_key('course', 'course')] + block_keys)
        for compat_module in 'completion_aggregator.core.compat', 'completion_aggregator.core.compat':
            patch = mock.patch(compat_module, stubcompat)
            patch.start()
            self.addCleanup(patch.stop)

        for idx in range(1, 51):
            block_key = course_key.make_usage_key('html', f'course-html{idx}')
            with freeze_time(f"2020-02-02T02:02:{idx}"):
                CourseModuleCompletion.objects.create(
                    id=idx,
                    user=user,
                    course_id=course_key,
                    content_id=block_key,
                )
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO completion_blockcompletion
                        (user_id, course_key, block_key, block_type, completion, created, modified)
                    VALUES
                        (%s, %s, %s, %s, 1.0, %s, %s);
                    """,
                    [
                        user.id,
                        course_key,
                        block_key,
                        block_key.block_type,
                        "0000-00-00 00:00:00",
                        "0000-00-00 00:00:00",
                    ]
                )

    @mock.patch("time.sleep")
    def test_migration_updates_created_modified(self, mock_sleep):
        cmc_count = CourseModuleCompletion.objects.all().count()
        c_count = BlockCompletion.objects.all().count()
        self.assertEqual(cmc_count, 50)
        self.assertEqual(c_count, 50)
        for block_key in self.block_keys:
            bc = BlockCompletion.objects.get(
                user=self.user,
                context_key=self.course_key,
                block_key=block_key,
                block_type=block_key.block_type,
                completion=1.0,
            )
            cmc = CourseModuleCompletion.objects.get(
                user=self.user,
                course_id=self.course_key,
                content_id=block_key,
            )
            self.assertNotEqual(bc.created, cmc.created)
            self.assertNotEqual(bc.modified, cmc.modified)
        _migrate_batch(11, 0.1)
        cmc_count = CourseModuleCompletion.objects.all().count()
        c_count = BlockCompletion.objects.all().count()
        self.assertEqual(cmc_count, 50)
        self.assertEqual(c_count, 50)
        self.assertEqual(mock_sleep.call_count, 5)
        for block_key in self.block_keys:
            bc = BlockCompletion.objects.get(
                user=self.user,
                context_key=self.course_key,
                block_key=block_key,
                block_type=block_key.block_type,
                completion=1.0,
            )
            cmc = CourseModuleCompletion.objects.get(
                user=self.user,
                course_id=self.course_key,
                content_id=block_key,
            )
            self.assertEqual(bc.created, cmc.created)
            self.assertEqual(bc.modified, cmc.modified)
