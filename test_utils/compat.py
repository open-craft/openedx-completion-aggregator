"""
Test compatibility layer that reduces dependence on edx-platform.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import collections

from mock import MagicMock

from completion.models import BlockCompletion

from .test_app.models import CohortMembership, CourseAccessRole, CourseEnrollment, CourseUserGroup


class StubCompat(object):
    """
    An AggregationUpdater with connections to edx-platform and modulestore
    replaced with local elements.
    """

    def __init__(self, blocks):
        self.blocks = blocks

    def init_course_block_key(self, modulestore, course_key):  # pylint: disable=unused-argument
        """
        Create a root usage key for the course.

        For the purposes of testing, we're just going by convention.
        """
        return course_key.make_usage_key('course', 'course')

    def init_course_blocks(self, user, course_block_key):  # pylint: disable=unused-argument
        """
        Not actually used in this implementation.

        Overridden here to prevent the default behavior, which relies on
        modulestore.
        """
        root_segments = course_block_key.block_id.split('-')
        return CompatCourseBlocks(
            *(block for block in self.blocks if block.block_id.split('-')[:len(root_segments)] == root_segments)
        )

    def get_affected_aggregators(self, course_blocks, changed_blocks):
        """
        Get all the aggregator blocks affected by a change to one of the given blocks.
        """
        affected = set()
        for block in course_blocks.blocks:
            if any(changed.block_id.startswith('{}-'.format(block.block_id)) for changed in changed_blocks):
                affected.add(block)
        return affected

    def get_block_completions(self, user, course_key):
        """
        Return all completions for the current course.
        """
        return BlockCompletion.objects.filter(user=user, course_key=course_key)

    def get_children(self, course_blocks, block_key):
        """
        Return children for the given block.
        """
        return [
            block for block in course_blocks.blocks if course_blocks.is_child(block, block_key)
        ]

    def get_modulestore(self):
        """
        This implementation doesn't need a modulestore.

        The user will still call methods on it, so we provide a MagicMock.
        """
        return MagicMock()

    def course_enrollment_model(self):
        """
        Return this replacement for CourseEnrollment
        """
        return CourseEnrollment

    def get_mobile_only_courses(self):
        return MagicMock()

    def get_item_not_found_error(self):
        """
        Use ValueError as a replacement for modulestore's ItemNotFoundError
        """
        return ValueError

    def get_users_enrolled_in(self, course_key):  # pylint: disable=unused-argument
        """
        Return a mock queryset of users enrolled in course.
        """
        mock = MagicMock()
        # Simulate 5 users enrolled in course
        mock.count.return_value = 5
        return mock

    def course_access_role_model(self):
        """
        Return this replacement for CourseAccessRole
        """
        return CourseAccessRole

    def course_user_group(self):
        """
        Return this replacement for CourseUserGroup
        """
        return CourseUserGroup

    def cohort_membership_model(self):
        """
        Return this replacement for CohortMembership
        """
        return CohortMembership


CourseTreeNode = collections.namedtuple('CourseTreeNode', ['block', 'children'])


class CompatCourseBlocks(object):
    """
    Given a list of blocks, creates a course tree for testing.

    In this course tree, blocks are implicitly nested by their block id, with
    segments separated by hyphens.
    """

    def __init__(self, *blocks):
        self.blocks = blocks

    def is_child(self, child, parent):
        parent_segments = parent.block_id.split('-')
        child_segments = child.block_id.split('-')
        return (
            len(child_segments) == len(parent_segments) + 1
            and child_segments[:-1] == parent_segments
        )
