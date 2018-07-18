"""

Aggregator service.

This service periodically determines which stale_blocks need updating, and
enqueues tasks to perform those updates.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import logging

import six

from django.db import transaction

from . import models, utils
from .tasks import aggregation_tasks

log = logging.getLogger(__name__)

EnrollmentTuple = collections.namedtuple('EnrollmentTuple', ['username', 'course_key'])

MAX_KEYS_PER_TASK = 128


def perform_aggregation():
    """
    Enqueues tasks to reaggregate modified completions.

    When blocks are completed, they mark themselves as stale.  This function
    collects all stale blocks for each enrollment, and enqueues a single
    recalculation of all aggregators containing those stale blocks.
    """
    with transaction.atomic():
        stale_queryset = models.StaleCompletion.objects.filter(resolved=False)
        stale_blocks = collections.defaultdict(set)
        forced_updates = set()
        for stale in stale_queryset:
            enrollment = EnrollmentTuple(
                username=stale.username,
                course_key=stale.course_key,
            )
            if stale.block_key is None:
                stale_blocks[enrollment] = utils.BagOfHolding()
            blocks = stale_blocks[enrollment]
            if isinstance(blocks, utils.BagOfHolding) or len(blocks) <= MAX_KEYS_PER_TASK:
                # We can stop adding once we have exceeded the maximum number of keys per task.
                stale_blocks[enrollment].add(stale.block_key)
            if stale.force:
                forced_updates.add(enrollment)

        log.info("Performing aggregation update for %s user enrollments", len(stale_blocks))
        for enrollment in stale_blocks:
            if isinstance(stale_blocks[enrollment], utils.BagOfHolding):
                blocks = []
            elif len(stale_blocks[enrollment]) > MAX_KEYS_PER_TASK:
                # Limit the number of block_keys we will add to a task,
                # because celery has a task size limit.  Instead, just
                # reprocess the whole course.
                blocks = []
            else:
                blocks = [six.text_type(block_key) for block_key in stale_blocks[enrollment]]
            aggregation_tasks.update_aggregators.delay(
                username=enrollment.username,
                course_key=six.text_type(enrollment.course_key),
                block_keys=blocks,
                force=enrollment in forced_updates,
            )


def perform_cleanup():
    """
    Remove resolved StaleCompletion objects.
    """
    return models.StaleCompletion.objects.filter(resolved=True).delete()
