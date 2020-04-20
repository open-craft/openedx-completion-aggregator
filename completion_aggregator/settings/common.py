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
