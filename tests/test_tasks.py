# -*- coding: utf-8 -*-

"""
Tests for the `openedx-completion-aggregator` tasks.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import unittest

import ddt
import mock
from completion.models import BlockCompletion
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from freezegun import freeze_time
from opaque_keys.edx.keys import CourseKey

from completion_aggregator.tasks.aggregation_tasks import _migrate_batch
from test_utils.compat import StubCompat

try:
    from progress.models import CourseModuleCompletion

    RUNNING_IN_PLATFORM = True
except ImportError:
    RUNNING_IN_PLATFORM = False


@ddt.ddt
@unittest.skipUnless(
    RUNNING_IN_PLATFORM,
    "CourseModuleCompletion not available. Please run with edx-platform context.",
)
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
        self.user = user = User.objects.create_user("test", password="test")
        self.course_key = course_key = CourseKey.from_string('course-v1:edx+course+test')
        self.block_keys = block_keys = [
            course_key.make_usage_key('html', 'course-html{}'.format(idx))
            for idx in range(1, 51)
        ]
        stubcompat = StubCompat([course_key.make_usage_key('course', 'course')] + block_keys)
        for compat_module in 'completion_aggregator.core.compat', 'completion_aggregator.core.compat':
            patch = mock.patch(compat_module, stubcompat)
            patch.start()
            self.addCleanup(patch.stop)

        for idx in range(1, 51):
            block_key = course_key.make_usage_key('html', 'course-html{}'.format(idx))
            with freeze_time("2020-02-02T02:02:{}".format(idx)):
                CourseModuleCompletion.objects.create(
                    id=idx,
                    user=user,
                    course_id=course_key,
                    content_id=block_key,
                )
            with freeze_time("2019-02-02T02:02:{}".format(idx)):
                BlockCompletion.objects.create(
                    user=user,
                    course_key=course_key,
                    block_key=block_key,
                    block_type=block_key.block_type,
                    completion=1.0,
                )

    def test_migration_updates_created_modified(self):
        cmc_count = CourseModuleCompletion.objects.all().count()
        c_count = BlockCompletion.objects.all().count()
        self.assertEqual(cmc_count, 50)
        self.assertEqual(c_count, 50)
        for block_key in self.block_keys:
            bc = BlockCompletion.objects.get(
                user=self.user,
                course_key=self.course_key,
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
        _migrate_batch(1, 51)
        cmc_count = CourseModuleCompletion.objects.all().count()
        c_count = BlockCompletion.objects.all().count()
        self.assertEqual(cmc_count, 50)
        self.assertEqual(c_count, 50)
        for block_key in self.block_keys:
            bc = BlockCompletion.objects.get(
                user=self.user,
                course_key=self.course_key,
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
