"""
Handlers for signals emitted by block completion models.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from django.conf import settings
from django.db.models.signals import post_save

from . import aggregator, compat, models
from .tasks import handler_tasks

log = logging.getLogger(__name__)


def register():
    """
    Register signal handlers.
    """
    post_save.connect(completion_updated_handler, sender=compat.get_aggregated_model())

    try:
        from xmodule.modulestore.django import SignalHandler
    except ImportError:
        log.warning(
            "Could not import modulestore signal handlers. Completion Aggregator not hooked up to edx-platform."
        )
    else:
        SignalHandler.course_published.connect(course_published_handler)
        SignalHandler.item_deleted.connect(item_deleted_handler)

    ginkgo_error_template = "%s signal not found. If this is a solutions/ginkgo server, this is expected."

    try:
        from openedx.core.djangoapps.course_groups.signals.signals import COHORT_MEMBERSHIP_UPDATED
    except ImportError:
        log.info(ginkgo_error_template, "COHORT_MEMBERSHIP_UPDATED")
    else:
        COHORT_MEMBERSHIP_UPDATED.connect(cohort_updated_handler)

    try:
        from student.signals.signals import ENROLLMENT_TRACK_UPDATED
    except ImportError:
        log.info(ginkgo_error_template, "ENROLLMENT_TRACK_UPDATED")
    else:
        ENROLLMENT_TRACK_UPDATED.connect(cohort_updated_handler)


# Signal handlers frequently ignore arguments passed to them.  No need to lint them.
# pylint: disable=unused-argument


def item_deleted_handler(usage_key, user_id, **kwargs):
    """
    Update aggregators when an item change happens.

    We cannot pass the usage key to the update_aggregators task, because the
    block is no longer part of the course graph, so we would be unable to find
    its parent blocks.
    """
    log.debug("Updating aggregators due to item_deleted signal")

    # Ordinarily we have to worry about losing course run information when
    # extracting a course_key from a usage_key, but the item_delete signal is
    # only fired from split-mongo, so it will always contain the course run.
    course_key = usage_key.course_key
    handler_tasks.mark_all_stale.delay(course_key=course_key)


def course_published_handler(course_key, **kwargs):
    """
    Update aggregators when a general course change happens.
    """
    log.debug("Updating aggregators due to course_published signal")
    handler_tasks.mark_all_stale.delay(course_key=course_key)


def cohort_updated_handler(user, course_key, **kwargs):
    """
    Update aggregators for a user when the user changes cohort or enrollment track.
    """
    log.debug("Updating aggregators due to cohort or enrollment update signal")
    handler_tasks.mark_all_stale.delay(course_key=course_key, users=[user])


def completion_updated_handler(signal, sender, instance, created, raw, using, update_fields, **kwargs):
    """
    Update aggregate completions based on a changed block.
    """
    if raw:  # pragma: no cover
        # Raw saves are performed when loading fixtures, and should not cause
        # cascading updates.  This is excluded from coverage, because the only
        # method django provides for loading fixtures is via a management
        # command.
        return

    log.debug(
        "Updating aggregators for %s in %s.  Updated block: %s",
        instance.user.username,
        instance.course_key,
        instance.block_key,
    )
    models.StaleCompletion.objects.create(
        username=instance.user.username,
        course_key=instance.course_key,
        block_key=instance.block_key
    )
    if not getattr(settings, 'COMPLETION_AGGREGATOR_ASYNC_AGGREGATION', False):
        aggregator.perform_aggregation()
        aggregator.perform_cleanup()
