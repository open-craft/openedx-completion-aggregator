"""
AWS settings for completion_aggregator.
"""

from __future__ import absolute_import, division, print_function, unicode_literals


def plugin_settings(settings):
    """
    Modify the provided settings object with settings specific to this plugin.
    """
    settings.COMPLETION_AGGREGATOR_BLOCK_TYPES = set(settings.ENV_TOKENS.get(
        'COMPLETION_AGGREGATOR_BLOCK_TYPES',
        settings.COMPLETION_AGGREGATOR_BLOCK_TYPES,
    ))

    settings.COMPLETION_AGGREGATOR_ASYNC_AGGREGATION = settings.ENV_TOKENS.get(
        'COMPLETION_AGGREGATOR_ASYNC_AGGREGATION',
        settings.COMPLETION_AGGREGATOR_ASYNC_AGGREGATION,
    )

    settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK = settings.ENV_TOKENS.get(
        'COMPLETION_AGGREGATOR_AGGREGATION_LOCK',
        settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK,
    )

    settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS = settings.ENV_TOKENS.get(
        'COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS',
        settings.COMPLETION_AGGREGATOR_AGGREGATION_LOCK_TIMEOUT_SECONDS,
    )

    settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK = settings.ENV_TOKENS.get(
        'COMPLETION_AGGREGATOR_CLEANUP_LOCK',
        settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK,
    )

    settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK_TIMEOUT_SECONDS = settings.ENV_TOKENS.get(
        'COMPLETION_AGGREGATOR_CLEANUP_LOCK_TIMEOUT_SECONDS',
        settings.COMPLETION_AGGREGATOR_CLEANUP_LOCK_TIMEOUT_SECONDS,
    )
