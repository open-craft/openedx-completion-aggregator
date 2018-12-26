"""

Aggregator service.

This service periodically determines which stale_blocks need updating, and
enqueues tasks to perform those updates.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import logging
import time

import six

from . import models, utils
from .tasks import aggregation_tasks

log = logging.getLogger(__name__)

EnrollmentTuple = collections.namedtuple('EnrollmentTuple', ['username', 'course_key'])

MAX_KEYS_PER_TASK = 16


def perform_aggregation(batch_size=10000, delay=0.0, limit=None, routing_key=None):
    """
    Enqueues tasks to reaggregate modified completions.

    When blocks are completed, they mark themselves as stale.  This function
    collects all stale blocks for each enrollment, and enqueues a single
    recalculation of all aggregators containing those stale blocks.

    batch_size (int|None) [default: 10000]:
        Maximum number of stale completions to fetch in a single query to the
        database.

    delay (float) [default: 0.0]:
        The amount of time to wait between sending batches of 1000 tasks to
        celery.

    limit (int|None) [default: None]:
        Maximum number of stale completions to process in a single run of this
        function.  None means process all outstanding StaleCompletions.

    routing_key (str|None) [default None]:
        A routing key to pass to celery for the update_aggregators tasks.  None
        means use the default routing key.
    """
    stale_queryset = models.StaleCompletion.objects.filter(resolved=False)
    task_options = {}
    if limit is None:
        limit = float('inf')

    try:
        min_id = stale_queryset.order_by('id')[0].id
        max_id = stale_queryset.order_by('-id')[0].id
    except IndexError:
        log.warning("No StaleCompletions to process. Exiting.")
        return
    if routing_key:
        task_options['routing_key'] = routing_key

    stale_blocks = collections.defaultdict(set)
    forced_updates = set()
    enqueued = 0
    for idx in six.moves.range(max_id, min([min_id + batch_size, max_id]) - 1, -1 * batch_size):
        if enqueued >= limit:
            break
        evaluated = stale_queryset.filter(id__gt=idx - batch_size, id__lte=idx)
        enqueued += len(evaluated)
        for stale in evaluated:
            enrollment = EnrollmentTuple(
                username=stale.username,
                course_key=stale.course_key,
            )
            if stale.block_key is None:
                stale_blocks[enrollment] = utils.BagOfHolding()
            blocks = stale_blocks[enrollment]
            if isinstance(blocks, utils.BagOfHolding) or len(blocks) <= MAX_KEYS_PER_TASK:
                # We can stop adding once we have exceeded the maximum number
                # of keys per task.  This keeps the memory usage of this
                # function down, and limits the size of the task signature sent
                # to celery.
                stale_blocks[enrollment].add(stale.block_key)
            if stale.force:
                forced_updates.add(enrollment)

    log.info("Performing aggregation update for %s user enrollments", len(stale_blocks))
    for idx, enrollment in enumerate(stale_blocks):
        if isinstance(stale_blocks[enrollment], utils.BagOfHolding):
            blocks = []
        elif len(stale_blocks[enrollment]) > MAX_KEYS_PER_TASK:
            blocks = []
        else:
            blocks = [six.text_type(block_key) for block_key in stale_blocks[enrollment]]
        aggregation_tasks.update_aggregators.apply_async(
            kwargs={
                'username': enrollment.username,
                'course_key': six.text_type(enrollment.course_key),
                'block_keys': blocks,
                'force': enrollment in forced_updates,
            },
            **task_options
        )
        if idx % 1000 == 999:
            if delay:
                time.sleep(delay)


def perform_cleanup():
    """
    Remove resolved StaleCompletion objects.
    """
    return models.StaleCompletion.objects.filter(resolved=True).delete()
