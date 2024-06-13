"""
Test the aggregator plugin settings.
"""
from django.conf import settings
from django.test import override_settings

from completion_aggregator.settings import aws as aws_settings


@override_settings(ENV_TOKENS={})
def test_production_settings():
    """
    Test that the completion aggregator production settings behave as expected
    """
    aws_settings.plugin_settings(settings)

    assert list(settings.ALLOWED_COMPLETION_AGGREGATOR_EVENT_TYPES.keys()) == ["progress", "completion"]
