"""
Asynchronous tasks for performing aggregation of completions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
from collections import namedtuple
from datetime import datetime

import pytz
from celery import shared_task
from celery_utils.logged_task import LoggedTask
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey
from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock

from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone

from .. import compat
from ..models import Aggregator, StaleCompletion
from ..utils import BagOfHolding

try:
    from progress.models import CourseModuleCompletion
    PROGRESS_IMPORTED = True
except ImportError:
    PROGRESS_IMPORTED = False

# SQLite doesn't support the ON DUPLICATE KEY syntax.  INSERT OR REPLACE will
# have a similar effect, but uses new primary keys.  The drawbacks of this are:
# * It will consume the available keyspace more quickly.
# * It will not preserve foreign keys pointing to our table.
# SQLite is only used in testing environments, so neither of these drawbacks
# poses an actual problem.

INSERT_OR_UPDATE_MYSQL = """
    INSERT INTO completion_blockcompletion
        (user_id, course_key, block_key, block_type, completion)
    VALUES
        (%s, %s, %s, %s, 1.0)
    ON DUPLICATE KEY UPDATE
        completion=VALUES(completion);
"""

INSERT_OR_UPDATE_SQLITE = """
    INSERT OR REPLACE
    INTO completion_blockcompletion
        (user_id, course_key, block_key, block_type, completion)
    VALUES
        (%s, %s, %s, %s, 1.0);
"""


OLD_DATETIME = pytz.utc.localize(datetime(1900, 1, 1, 0, 0, 0))

CompletionStats = namedtuple('CompletionStats', ['earned', 'possible', 'last_modified'])

log = logging.getLogger(__name__)


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
    try:
        updater = AggregationUpdater(user, course_key, compat.get_modulestore())
    except compat.get_item_not_found_error():
        log.exception("Course not found in modulestore.  Skipping aggregation for %s/%s.", user, course_key)
    except TypeError:
        log.exception("Could not parse modulestore data.  Skipping aggregation for %s/%s.", user, course_key)
    else:
        updater.update(block_keys, force)


def calculate_updated_aggregators(user, course_key, changed_blocks=frozenset(), force=False):
    try:
        updater = AggregationUpdater(user, course_key, compat.get_modulestore())
    except compat.get_item_not_found_error():
        log.exception("Course not found in modulestore.  Skipping aggregation for %s/%s.", user, course_key)
        return []
    except TypeError:
        log.exception("Could not parse modulestore data.  Skipping aggregation for %s/%s.", user, course_key)
        return []
    else:
        return updater.calculate_updated_aggregators(changed_blocks, force)


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
        # used to store all rows for update
        self.updated_aggregators = []
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
            return BagOfHolding()

    def calculate_updated_aggregators(self, changed_blocks=frozenset(), force=False):
        """
        Return updated aggregators without sumitting them to the database.

        And without clearing stale completions.
        """
        affected_aggregators = self.get_affected_aggregators(changed_blocks)
        self.update_for_block(self.course_block_key, affected_aggregators, force)
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
        mode = XBlockCompletionMode.get_mode(XBlock.load_class(block.block_type))
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


@shared_task
def migrate_batch(offset, batch_size):  # Cannot pass a queryset to a task.
    """
    Convert a batch of CourseModuleCompletions to BlockCompletions.

    Given an offset and batch_size, this task will:

    * Fetch a subset of the existing CourseModuleCompletions,
    * Update the BlockCompletions table
    """
    if not PROGRESS_IMPORTED:
        log.error("Cannot perform migration: CourseModuleCompletion not importable.")

    queryset = CourseModuleCompletion.objects.all().order_by('id')
    course_module_completions = queryset[offset:offset + batch_size]

    processed = {}  # Dict has format: {course: {user: [blocks]}
    insert_params = []
    for cmc in course_module_completions:
        try:
            course_key = CourseKey.from_string(cmc.course_id)
            block_key = UsageKey.from_string(cmc.content_id).map_into_course(course_key)
            block_type = block_key.block_type
        except InvalidKeyError:
            log.exception(
                "Could not migrate CourseModuleCompletion with values: %s",
                cmc.__dict__,
            )
            continue
        if course_key not in processed:
            processed[course_key] = set()
        if cmc.user not in processed[course_key]:
            processed[course_key].add(cmc.user)
        # Param order: (user_id, course_key, block_key, block_type)
        insert_params.append((cmc.user_id, cmc.course_id, cmc.content_id, block_type))
    if connection.vendor == 'mysql':
        sql = INSERT_OR_UPDATE_MYSQL
    else:
        sql = INSERT_OR_UPDATE_SQLITE
    with connection.cursor() as cur:
        cur.executemany(sql, insert_params)
    # Create aggregators later.
    stale_completions = []
    for course_key in processed:
        for user in processed[course_key]:
            stale_completions.append(
                StaleCompletion(
                    username=user.username,
                    course_key=course_key,
                    block_key=None,
                    force=True
                )
            )
    StaleCompletion.objects.bulk_create(
        stale_completions,
    )
    log.info("Completed progress migration batch from %s to %s", offset, offset + batch_size)
