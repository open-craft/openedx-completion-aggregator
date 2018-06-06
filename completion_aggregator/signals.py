"""
Handlers for signals emitted by block completion models.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import six

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save

from . import compat
from .models import Aggregator
from .tasks import update_aggregators

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
    for user in get_active_users(course_key):
        update_aggregators.delay(username=user.username, course_key=six.text_type(course_key), force=True)


def course_published_handler(course_key, **kwargs):
    """
    Update aggregators when a general course change happens.
    """
    log.debug("Updating aggregators due to course_published signal")
    for user in get_active_users(course_key):
        update_aggregators.delay(username=user.username, course_key=six.text_type(course_key), force=True)


def cohort_updated_handler(user, course_key, **kwargs):
    """
    Update aggregators for a user when the user changes cohort or enrollment track.
    """
    log.debug("Updating aggregators due to cohort or enrollment update signal")
    update_aggregators.delay(username=user.username, course_key=six.text_type(course_key), force=True)


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

    if not Aggregator.objects.filter(
            user=instance.user,
            course_key=instance.course_key,
            aggregation_name='course',
            last_modified__gte=instance.modified).exists():

        try:
            update_aggregators.delay(
                username=instance.user.username,
                course_key=six.text_type(instance.course_key),
                block_keys=[six.text_type(instance.block_key)],
            )
        except ImportError:
            log.warning("Completion Aggregator is not hooked up to edx-plaform.")


def get_active_users(course_key):
    """
    Return a list of users that have Aggregators in the course.
    """
    return get_user_model().objects.filter(aggregator__course_key=course_key).distinct()
