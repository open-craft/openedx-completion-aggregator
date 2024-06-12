"""
Common settings for completion_aggregator.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from event_routing_backends.utils.settings import event_tracking_backends_config


def plugin_settings(settings):
    """
    Modify the provided settings object with settings specific to this plugin.
    """
    # Emit feature allows to publish two kind of events progress and completion
    # This setting controls which type of event will be published to change the default behavior
    # the block type should be removed or added from the progress or completion list.
    settings.ALLOWED_COMPLETION_AGGREGATOR_EVENT_TYPES = {
        "progress": {
            "course",
            "chapter",
            "sequential",
            "vertical",
        },
        "completion": {
            "course",
            "chapter",
            "sequential",
            "vertical",
        }
    }
    settings.COMPLETION_AGGREGATOR_BLOCK_TYPES = {
        'course',
        'chapter',
        'sequential',
        'vertical',
    }

    settings.COMPLETION_AGGREGATOR_ASYNC_AGGREGATION = False

    # Names of the batch operations locks
    settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK = 'COMPLETION_AGGREGATOR_AGGREGATION_LOCK'
    settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK = 'COMPLETION_AGGREGATOR_CLEANUP_LOCK'

    # Define how long should the locks be kept. They are released after completing the operation, so there are two
    # possible scenarios for releasing the lock on timeout:
    # 1. The management command takes more than 1800s - in this case you should set a higher limit for the lock.
    # 2. The management command didn't exit successfully. You should check the logs to find out why.
    settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS = 1800
    settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK_TIMEOUT_SECONDS = 900

    # Enables the use of course blocks with a release date set to a future date in the course completion calculation.
    # By default, unreleased blocks are excluded from the aggregation, and course is considered 100% completed if all
    # user-viewable blocks are completed.
    # Notes:
    # 1. All courses should be reaggregated for the changes to take effect.
    # 2. It's not possible to revert this change by reaggregation without manually removing existing Aggregators.
    settings.COMPLETION_AGGREGATOR_AGGREGATE_UNRELEASED_BLOCKS = False

    # Whitelist the aggregator events for use with event routing backends xAPI backend.
    enabled_aggregator_events = [
        f'openedx.completion_aggregator.{event_type}.{block_type}'

        for event_type in settings.ALLOWED_COMPLETION_AGGREGATOR_EVENT_TYPES
        for block_type in settings.ALLOWED_COMPLETION_AGGREGATOR_EVENT_TYPES[event_type]
    ]
    settings.EVENT_TRACKING_BACKENDS_ALLOWED_XAPI_EVENTS += enabled_aggregator_events
    settings.EVENT_TRACKING_BACKENDS.update(event_tracking_backends_config(
        settings.EVENT_TRACKING_BACKENDS_ALLOWED_XAPI_EVENTS,
        settings.EVENT_TRACKING_BACKENDS_ALLOWED_CALIPER_EVENTS,
    ))
