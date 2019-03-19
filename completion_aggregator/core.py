"""
Core aggregator functionality.

This is the engine that takes BlockCompletion objects and
converts them to Aggregators.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
from collections import namedtuple
from datetime import datetime

import pytz
import six
from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock
from xblock.plugin import PluginMissingError

from django.utils import timezone

from . import compat
from .cachegroup import CacheGroup
from .models import Aggregator, StaleCompletion
from .utils import BagOfHolding

OLD_DATETIME = pytz.utc.localize(datetime(1900, 1, 1, 0, 0, 0))
UPDATER_CACHE_TIMEOUT = 600  # 10 minutes

CacheEntry = namedtuple('CacheEntry', ['course_blocks', 'root_block'])
CompletionStats = namedtuple('CompletionStats', ['earned', 'possible', 'last_modified'])

log = logging.getLogger(__name__)


class UpdaterCache(object):
    """
    Cache course blocks for Aggregation Updater.

    Uses `completion_aggregator.cachegroup.CacheGroup` to allow bulk
    invalidation by course_key.
    """

    cache_key_template = "completion_aggregator.updater.{user_id}-{course_key}-{root_block}"

    def __init__(self, user_id, course_key, root_block):
        """
        Create a new Updater Cache for the provided user_id, course_key, and root_block.
        """
        self.user_id = user_id
        self.course_key = course_key
        self.root_block = root_block

    def get(self):
        """
        Return the cached BlockStructure and root block for the current cache entry.
        """
        return CacheGroup().get(self.cache_key)

    def set(self, value):
        """
        Cache a BlockStructure and root block for the current cache entry.

        Sets the group to `str(self.course_key)`.
        """
        group = six.text_type(self.course_key)
        CacheGroup().set(group, self.cache_key, value, timeout=UPDATER_CACHE_TIMEOUT)

    def touch(self):
        """
        Update the timeout for a given cache key.
        """
        CacheGroup().touch(self.cache_key, timeout=UPDATER_CACHE_TIMEOUT)

    @property
    def cache_key(self):
        """
        Create a key to identify the current cache entry.
        """
        return self.cache_key_template.format(
            user_id=self.user_id,
            course_key=self.course_key,
            root_block=self.root_block or 'COURSE',
        )


CourseBlocksEntry = namedtuple('CourseBlocksEntry', ['children', 'aggregators'])


class AggregationUpdater(object):
    """
    Class to update aggregators for a given course and user.
    """

    def __init__(self, user, course_key, modulestore, root_block=None):
        """
        Create an aggregation updater for the given user and course.

        Also takes a modulestore instance.
        """
        self.user = user
        self.course_key = course_key
        self.raw_root_block = root_block
        self.cache = UpdaterCache(self.user.id, self.course_key, self.raw_root_block)

        cache_entry = self.cache.get()
        if cache_entry:
            self.using_cache = True
            self.course_blocks = cache_entry.course_blocks
            self.root_block = cache_entry.root_block
        else:
            self.using_cache = False
            with modulestore.bulk_operations(self.course_key):
                if self.raw_root_block:
                    self.root_block = self.raw_root_block
                else:
                    self.root_block = compat.init_course_block_key(modulestore, self.course_key)
                self.course_blocks = self.format_course_blocks(
                    compat.init_course_blocks(self.user, self.root_block),
                    self.root_block
                )
        self.aggregators = {
            aggregator.block_key: aggregator for aggregator in Aggregator.objects.filter(
                user=self.user,
                course_key=self.course_key,
            )
        }
        # used to store all rows for update
        self.updated_aggregators = []
        self.block_completions = {
            completion.block_key.map_into_course(self.course_key): completion
            for completion in compat.get_block_completions(self.user, self.course_key)
        }

    def format_course_blocks(self, course_blocks, root_block):
        """
        Simplify the BlockStructure to have the following format.

            {
                block_key: CourseBlocksEntry(
                    children=block_key[],
                    aggregators=block_key[]
                )
            }

        """
        structure = {}

        def populate(structure, block):
            if block not in structure:
                structure[block] = CourseBlocksEntry(
                    children=compat.get_children(course_blocks, block),
                    aggregators=compat.get_block_aggregators(course_blocks, block),
                )
                for child in structure[block].children:
                    populate(structure, child)

        populate(structure, root_block)
        return structure

    def set_cache(self):
        """
        Cache updater values to prevent calling course_blocks api.

        Calling the course_blocks api is time-consuming, primarily due to
        the StudentViewTransformer, which calls student_view_data() on each
        block.

        We only use this when the updater is being used in a request cycle.
        If we cached during bulk aggregation, the cache miss rate would be
        high, as could the number of course structures cached, especially if
        staff had been making course updates.
        """
        if self.using_cache:
            self.cache.touch()
        entry = CacheEntry(course_blocks=self.course_blocks, root_block=self.root_block)
        self.cache.set(entry)

    def get_affected_aggregators(self, changed_blocks):
        """
        Return the set of aggregator blocks that may need updating.
        """
        if changed_blocks:
            affected_aggregators = set()
            for block in changed_blocks:
                if block not in self.course_blocks:
                    # The course structure has changed.  Conservatively recalculate the whole tree.
                    return BagOfHolding()
                affected_aggregators.update(self.course_blocks[block].aggregators)
            return affected_aggregators
        else:
            return BagOfHolding()

    def calculate_updated_aggregators(self, changed_blocks=frozenset(), force=False):
        """
        Return updated aggregators without sumitting them to the database.

        And without clearing stale completions.
        """
        affected_aggregators = self.get_affected_aggregators(changed_blocks)
        self.update_for_block(self.root_block, affected_aggregators, force)
        return self.updated_aggregators

    def update(self, changed_blocks=frozenset(), force=False):
        """
        Update the aggregators for the course.

        Takes a set of completable blocks that have been recently
        updated to inform how to perform the update. If supplied, only
        the aggregators containing those blocks will be
        updated. Otherwise, the entire course tree will be updated.
        """
        start = timezone.now()
        updated_aggregators = self.calculate_updated_aggregators(changed_blocks, force)
        Aggregator.objects.bulk_create_or_update(updated_aggregators)
        self.resolve_stale_completions(changed_blocks, start)

    def update_for_block(self, block, affected_aggregators, force=False):
        """
        Recursive function to perform updates for a given block.

        Dispatches to an appropriate method given the block's completion_mode.
        """
        try:
            mode = XBlockCompletionMode.get_mode(XBlock.load_class(block.block_type))
        except PluginMissingError:
            # Do not count blocks that aren't registered
            mode = XBlockCompletionMode.EXCLUDED
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
            obj = self.aggregators.get(block)
            if obj:
                return CompletionStats(earned=obj.earned, possible=obj.possible, last_modified=obj.last_modified)
        for child in self.course_blocks[block].children:
            (earned, possible, modified) = self.update_for_block(child, affected_aggregators, force)
            total_earned += earned
            total_possible += possible
            if modified is not None:
                last_modified = max(last_modified, modified)
        if self._aggregator_needs_update(block, last_modified, force):
            if total_possible == 0.0:
                percent = 1.0
            else:
                percent = total_earned / total_possible
            Aggregator.objects.validate(self.user, self.course_key, block)
            if block not in self.aggregators:
                aggregator = Aggregator(
                    user=self.user,
                    course_key=self.course_key,
                    block_key=block,
                    aggregation_name=block.block_type,
                    earned=total_earned,
                    possible=total_possible,
                    percent=percent,
                    last_modified=last_modified,
                )
                self.aggregators[block] = aggregator
            else:
                aggregator = self.aggregators[block]
                aggregator.earned = total_earned
                aggregator.possible = total_possible
                aggregator.percent = percent
                aggregator.last_modified = last_modified
                aggregator.modified = timezone.now()
            self.updated_aggregators.append(aggregator)
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

    def resolve_stale_completions(self, changed_blocks, start):
        """
        Find all StaleCompletions resolved by this task and mark them resolved.
        """
        queryset = StaleCompletion.objects.filter(
            username=self.user.username,
            course_key=self.course_key,
            modified__lt=start,
        )
        if changed_blocks:
            queryset = queryset.filter(block_key__in=changed_blocks)
        queryset.update(resolved=True)


def calculate_updated_aggregators(user, course_key, changed_blocks=frozenset(), root_block=None, force=False):
    """
    Calculate latest values without saving to the database.

    This is generally called from a direct user request, so we cache the updater
    for faster access on subsequent requests.
    """
    try:
        updater = AggregationUpdater(user, course_key, compat.get_modulestore(), root_block=root_block)
        updater.set_cache()
    except compat.get_item_not_found_error():
        log.exception("Course not found in modulestore.  Skipping aggregation for %s/%s.", user, course_key)
        return []
    except TypeError:
        log.exception("Could not parse modulestore data.  Skipping aggregation for %s/%s.", user, course_key)
        return []
    else:
        return updater.calculate_updated_aggregators(changed_blocks, force)


def update_aggregators(user, course_key, block_keys=frozenset(), force=False):
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
    try:
        updater = AggregationUpdater(user, course_key, compat.get_modulestore())
    except compat.get_item_not_found_error():
        log.exception("Course not found in modulestore.  Skipping aggregation for %s in %s.", user, course_key)
        StaleCompletion.objects.filter(username=user.username, course_key=course_key).update(resolved=True)
    except TypeError:
        log.exception("Could not parse modulestore data.  Skipping aggregation for %s in %s.", user, course_key)
        StaleCompletion.objects.filter(username=user.username, course_key=course_key).update(resolved=True)
    else:
        updater.update(block_keys, force)
