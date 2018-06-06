"""
Asynchronous tasks.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
from collections import namedtuple
from datetime import datetime

import pytz
from celery import shared_task
from celery_utils.logged_task import LoggedTask
from opaque_keys.edx.keys import CourseKey, UsageKey
from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock

from django.contrib.auth.models import User

from . import compat
from .models import Aggregator

OLD_DATETIME = pytz.utc.localize(datetime(1900, 1, 1, 0, 0, 0))

log = logging.getLogger(__name__)


CompletionStats = namedtuple('CompletionStats', ['earned', 'possible', 'last_modified'])


class _BagOfHolding(object):
    """
    A container that contains everything.
    """

    def __contains__(self, value):
        return True


@shared_task(task=LoggedTask)
def update_aggregators(username, course_key, block_keys=(), force=False):
    """
    Update aggregators for the specified enrollment (user + course).

    Parameters
    ----------
        username (str):
            The user whose aggregators need updating.
        course_key (str):
            The course in which the aggregators need updating.
        block_key (list[str]):
            A list of completable blocks that have changed.
        force (bool):
            If True, update aggregators even if they are up-to-date.

    Takes a collection of block_keys that have been updated, to enable future
    optimizations in how aggregators are recalculated.

    """
    user = User.objects.get(username=username)
    course_key = CourseKey.from_string(course_key)
    block_keys = set(UsageKey.from_string(key).map_into_course(course_key) for key in block_keys)
    log.info("Updating aggregators in %s for %s. Changed blocks: %s", course_key, user.username, block_keys)
    return _update_aggregators(user, course_key, block_keys, force)


def _update_aggregators(user, course_key, block_keys=frozenset(), force=False):
    """
    Update the aggregators for the specified enrollment (user + course).

    This is the workhorse function for the update_aggregators task, taking its
    arguments strongly typed.

    Parameters
    ----------
        user (django.contrib.auth.models.User):
            The user whose aggregators need updating.
        course_key (opaque_keys.edx.keys.CourseKey):
            The course in which the aggregators need updating.
        block_keys (list[opaque_keys.edx.keys.UsageKey]):
             A list of completable blocks that have changed.
        force (bool):
            If True, update aggregators even if they are up-to-date.

    """
    updater = AggregationUpdater(user, course_key, compat.get_modulestore())
    updater.update(block_keys, force)


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
            self.course_block_key = compat.init_course_block_key(modulestore, self.course_key)
            self.course_blocks = compat.init_course_blocks(self.user, self.course_block_key)

        self.aggregators = {
            aggregator.block_key: aggregator for aggregator in Aggregator.objects.filter(
                user=self.user,
                course_key=self.course_key,
            )
        }
        self.block_completions = {
            completion.block_key.map_into_course(self.course_key): completion
            for completion in compat.get_block_completions(self.user, self.course_key)
        }

    def get_affected_aggregators(self, changed_blocks):
        """
        Return the set of aggregator blocks that may need updating.
        """
        if changed_blocks:
            return compat.get_affected_aggregators(self.course_blocks, changed_blocks)
        else:
            return _BagOfHolding()

    def update(self, changed_blocks=frozenset(), force=False):
        """
        Update the aggregators for the course.

        Takes a set of completable blocks that have been recently
        updated to inform how to perform the update. If supplied, only
        the aggregators containing those blocks will be
        updated. Otherwise, the entire course tree will be updated.
        """
        affected_aggregators = self.get_affected_aggregators(changed_blocks)
        self.update_for_block(self.course_block_key, affected_aggregators, force)

    def update_for_block(self, block, affected_aggregators, force=False):
        """
        Recursive function to perform updates for a given block.

        Dispatches to an appropriate method given the block's completion_mode.
        """
        mode = getattr(XBlock.load_class(block.block_type), 'completion_mode', XBlockCompletionMode.COMPLETABLE)
        if mode == XBlockCompletionMode.EXCLUDED:
            return self.update_for_excluded()
        elif mode == XBlockCompletionMode.COMPLETABLE:
            return self.update_for_completable(block)
        elif mode == XBlockCompletionMode.AGGREGATOR:
            return self.update_for_aggregator(block, affected_aggregators, force)
        else:
            raise ValueError("Invalid completion mode {}".format(mode))

    def update_for_aggregator(self, block, affected_aggregators, force):
        """
        Calculate the new completion values for an aggregator.
        """
        total_earned = 0.0
        total_possible = 0.0
        last_modified = OLD_DATETIME

        if block not in affected_aggregators:
            try:
                obj = Aggregator.objects.get(user=self.user, course_key=self.course_key, block_key=block)
            except Aggregator.DoesNotExist:
                pass
            else:
                return CompletionStats(earned=obj.earned, possible=obj.possible, last_modified=obj.last_modified)
        for child in compat.get_children(self.course_blocks, block):
            (earned, possible, modified) = self.update_for_block(child, affected_aggregators, force)
            total_earned += earned
            total_possible += possible
            last_modified = max(last_modified, modified)
        if self._aggregator_needs_update(block, last_modified, force):
            obj, _ = Aggregator.objects.submit_completion(
                user=self.user,
                course_key=self.course_key,
                block_key=block,
                aggregation_name=block.block_type,
                earned=total_earned,
                possible=total_possible,
                last_modified=last_modified,
            )
            self.aggregators[obj.block_key] = obj
        return CompletionStats(earned=total_earned, possible=total_possible, last_modified=last_modified)

    def update_for_excluded(self):
        """
        Return a sentinel empty completion value for excluded blocks.
        """
        return CompletionStats(earned=0.0, possible=0.0, last_modified=OLD_DATETIME)

    def update_for_completable(self, block):
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

    def _aggregator_needs_update(self, block, modified, force):
        """
        Return True if the given aggregator block needs to be updated.

        This method assumes that the block has already been determined to be an aggregator.
        """
        if Aggregator.block_is_registered_aggregator(block):
            agg = self.aggregators.get(block)
            if agg is None or force:
                return True
            return getattr(agg, 'last_modified', OLD_DATETIME) < modified
        return False
