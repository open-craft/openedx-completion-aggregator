"""
Common settings for completion_aggregator.
"""

from __future__ import absolute_import, division, print_function, unicode_literals


def plugin_settings(settings):
    """
    Modify the provided settings object with settings specific to this plugin.
    """
    settings.COMPLETION_AGGREGATOR_BLOCK_TYPES = {
        'course',
        'chapter',
        'sequential',
        'vertical',
    }

    # Emit feature publishes progress events to track aggregated completion.
    # Defaults to the full set of block types subject to completion aggregation.
    # Block types may be removed from this list to limit the tracking log events emitted.
    settings.COMPLETION_AGGREGATOR_TRACKING_EVENT_TYPES = settings.COMPLETION_AGGREGATOR_BLOCK_TYPES

    # Synchronous completion aggregation is enabled by default
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
