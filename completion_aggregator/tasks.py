"""
Asynchronous tasks.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from collections import namedtuple
from datetime import datetime

import pytz
from celery import shared_task
from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock

from django.conf import settings

from .models import Aggregator

OLD_DATETIME = pytz.utc.localize(datetime(1900, 1, 1, 0, 0, 0))


CompletionStats = namedtuple('CompletionStats', ['earned', 'possible', 'last_modified'])  # pylint: disable=invalid-name


@shared_task
def update_aggregators(user, course_key, block_keys=frozenset()):  # pylint: disable=unused-argument
    """
    Update aggregators for the specified course.

    Takes a collection of block_keys that have been updated, to enable
    future optimizations in how aggregators are recalculated.
    """
    from xmodule.modulestore.django import modulestore   # pylint: disable=import-error

    updater = AggregationUpdater(user, course_key, modulestore())
    updater.update(block_keys)


class AggregationUpdater(object):
    """
    Class to update aggregators for a given course and user.
    """

    def __init__(self, user, course_key, modulestore):
        """
        Create an aggregation updater for the given user and course.

        Also takes a modulestore instance.
        """
        self.user = user
        self.course_key = course_key
        with modulestore.bulk_operations(self.course_key):
            self.course_block_key = self.init_course_block_key(modulestore, self.course_key)
            self.course_blocks = self.init_course_blocks(self.user, self.course_block_key)
        self.aggregators = {
            aggregator.block_key: aggregator for aggregator in Aggregator.objects.filter(
                user=self.user,
                course_key=self.course_key,
            )
        }
        self.block_completions = {}
        for completion in self._get_block_completions():
            blk = completion.block_key
            if blk.course_key.run is None:
                if blk.course_key.org == self.course_key.org and blk.course_key.course == self.course_key.course:
                    blk = blk.map_into_course(self.course_key)
            self.block_completions[blk] = completion

    def update(self, changed_blocks=frozenset()):
        """
        Update the aggregators for the course.

        Takes a set of completable blocks that have been recently updated to
        inform how to perform the update.  Currently no optimizations are
        performed based on this information, but in the future they may help
        cut down on the amount of work performed.
        """
        self.update_for_block(self.course_block_key, changed_blocks)

    def update_for_block(self, block, changed_blocks):
        """
        Recursive function to perform updates for a given block.

        Dispatches to an appropriate method given the block's completion_mode.
        """
        mode = getattr(XBlock.load_class(block.block_type), 'completion_mode', XBlockCompletionMode.COMPLETABLE)
        if mode == XBlockCompletionMode.EXCLUDED:
            return self.update_for_excluded()
        elif mode == XBlockCompletionMode.COMPLETABLE:
            return self.update_for_completable(block, changed_blocks)
        elif mode == XBlockCompletionMode.AGGREGATOR:
            return self.update_for_aggregator(block, changed_blocks)

    def update_for_aggregator(self, block, changed_blocks):
        """
        Calculate the new completion values for an aggregator.
        """
        total_earned = 0.0
        total_possible = 0.0
        last_modified = OLD_DATETIME
        for child in self._get_children(block):
            completion = self.update_for_block(child, changed_blocks)
            total_earned += completion.earned
            total_possible += completion.possible
            last_modified = max(last_modified, completion.last_modified)
        if self._aggregator_needs_update(block, last_modified):
            Aggregator.objects.submit_completion(
                user=self.user,
                course_key=self.course_key,
                block_key=block,
                aggregation_name=block.block_type,
                earned=total_earned,
                possible=total_possible,
                last_modified=last_modified,
            )
        return CompletionStats(earned=total_earned, possible=total_possible, last_modified=last_modified)

    def update_for_excluded(self):
        """
        Return a sentinel empty completion value for excluded blocks.
        """
        return CompletionStats(earned=0.0, possible=0.0, last_modified=OLD_DATETIME)

    def update_for_completable(self, block, changed_blocks):  # pylint: disable=unused-argument
        """
        Return the block completion value for a given completable block.
        """
        completion = self.block_completions.get(block)
        if completion:
            earned = completion.completion
            last_modified = completion.modified
        else:
            earned = 0.0
            last_modified = OLD_DATETIME
        return CompletionStats(earned=earned, possible=1.0, last_modified=last_modified)

    def _aggregator_needs_update(self, block, modified):
        """
        Return True if the given aggregator block needs to be updated.

        This method assumes that the block has already been determined to be an aggregator.
        """
        agg = self.aggregators.get(block)
        return is_registered_aggregator(block) and getattr(agg, 'last_modified', OLD_DATETIME) < modified

    # Dependency isolation methods

    def init_course_block_key(self, modulestore, course_key):
        """
        Return a UsageKey for the root course block.
        """
        # pragma: no-cover
        return modulestore.make_course_usage_key(course_key)

    def init_course_blocks(self, user, course_block_key):
        """
        Return a BlockStructure representing the course.

        Blocks must have the following attributes:

            .location
            .block_type
        """
        # pragma: no-cover
        from lms.djangoapps.course_blocks.api import get_course_blocks  # pylint: disable=import-error
        return get_course_blocks(user, course_block_key)

    def _get_block_completions(self):
        """
        Return the list of BlockCompletions.

        Each must have the following attributes:

            .block_key (UsageKey)
            .modified (datetime)
            .completion
        """
        from completion.models import BlockCompletion  # pylint: disable=import-error
        return BlockCompletion.objects.filter(
            user=self.user,
            course_key=self.course_key,
        )

    def _get_children(self, block_key):
        """
        Return a list of blocks that are direct children of the specified block.

        ``course_blocks`` is not imported here, but it is hard to replicate
        without access to edx-platform, so tests will want to stub it out.
        """
        return self.course_blocks.get_children(block_key)


def is_registered_aggregator(block_key):
    """
    Return True if the block is registered to aggregate completions.
    """
    return block_key.block_type in settings.COMPLETION_AGGREGATOR_BLOCK_TYPES
