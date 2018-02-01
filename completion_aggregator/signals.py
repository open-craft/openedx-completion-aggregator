"""
Handlers for signals emitted by block completion models.
"""

import logging

from django.db.models.signals import post_save

from completion_aggregator.models import Aggregator
from completion_aggregator.tasks import update_aggregators

log = logging.getLogger(__name__)


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

    log.info(
        "Updating aggregators for %s/%s.  Updated block: %s",
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
                user=instance.user,
                course_key=instance.course_key,
                block_keys={instance.block_key},
            )
        except ImportError:
            log.warning("Completion Aggregator is not hooked up to edx-plaform.")


post_save.connect(completion_update_handler, sender='completion.BlockCompletion')
