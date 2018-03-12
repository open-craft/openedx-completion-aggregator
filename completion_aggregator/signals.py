"""
Handlers for signals emitted by block completion models.
"""

import logging

from django.conf import settings
from django.db.models.signals import post_save

log = logging.getLogger(__name__)


def _get_aggregated_model():
    """
    Return a string naming the model that we are aggregating.

    Normally, this will be 'completion.BlockCompletion', but tests will need to
    override it to avoid hooking into edx-platform.
    """
    return getattr(settings, 'COMPLETION_AGGREGATED_MODEL_OVERRIDE', 'completion.BlockCompletion')


def completion_update_handler(signal, sender, instance, created, raw, using, update_fields, **kwargs):  # pylint: disable=unused-argument
    """
    Update aggregate completions based on a changed block.
    """
    if raw:  # pragma: no cover
        # Raw saves are performed when loading fixtures, and should not cause
        # cascading updates.  This is excluded from coverage, because the only
        # method django provides for loading fixtures is via a management
        # command.
        return

    # The implementation for this will be handled in OC-3098.
    log.info(
        "Updating aggregators for %s/%s.  Updated block: %s",
        instance.user.username,
        instance.course_key,
        instance.block_key,
    )


post_save.connect(completion_update_handler, sender=_get_aggregated_model())
