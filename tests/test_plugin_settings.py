"""
Test the aggregator plugin settings.
"""
from event_routing_backends.settings import common as erb_settings

from django.conf import settings
from django.test import override_settings

from completion_aggregator.settings import aws as aws_settings
from completion_aggregator.settings import common as common_settings


@override_settings(ENV_TOKENS={})
def test_production_settings():
    """
    Test that the completion aggregator production settings behave as expected
    """
    aws_settings.plugin_settings(settings)

    assert settings.COMPLETION_AGGREGATOR_TRACKING_EVENT_TYPES == settings.COMPLETION_AGGREGATOR_BLOCK_TYPES


def test_event_tracking_backends():
    """
    Test that the completion aggregator events are whitelisted on the ERB backends.
    """
    # Event Routing Backend settings must be loaded first.
    erb_settings.plugin_settings(settings)
    common_settings.plugin_settings(settings)

    transformer_options = settings.EVENT_TRACKING_BACKENDS['event_transformer']['OPTIONS']
    toplevel_whitelist = set(transformer_options['processors'][0]['OPTIONS']['whitelist'])
    xapi_whitelist = set(transformer_options['backends']['xapi']['OPTIONS']['processors'][0]['OPTIONS']['whitelist'])

    assert toplevel_whitelist, "No whitelist found in event_transformer processors?"
    assert xapi_whitelist, "No whitelist found in event_transformer processors?"

    expected_events = {
        'openedx.completion_aggregator.progress.course',
        'openedx.completion_aggregator.progress.chapter',
        'openedx.completion_aggregator.progress.sequential',
        'openedx.completion_aggregator.progress.vertical',
    }

    # Ensure expected_events is a subset of these whitelists
    assert expected_events < toplevel_whitelist, "Aggregator events not found in event_transformer whitelist"
    assert expected_events < xapi_whitelist, "Aggregator events not found in xapi whitelist"


def test_performance_tuning_settings():
    """
    Test that the performance tuning settings are properly set by plugin_settings.
    """
    # Reset settings to ensure we're testing fresh
    if hasattr(settings, 'COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT'):
        delattr(settings, 'COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT')
    if hasattr(settings, 'COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE'):
        delattr(settings, 'COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE')

    common_settings.plugin_settings(settings)

    # Verify the settings are set with correct defaults
    assert settings.COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT == 600, \
        "COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT should default to 600 seconds"
    assert settings.COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE is False, \
        "COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE should default to False"
