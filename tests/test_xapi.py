"""
Test the completion aggregator transformers.
"""
import os
from unittest.mock import patch
from uuid import UUID

import ddt
from event_routing_backends.processors.xapi.tests.test_transformers import XApiTransformersFixturesTestMixin
from event_routing_backends.settings import common as erb_settings

from django.conf import settings
from django.test import TestCase

from completion_aggregator.settings import common as common_settings


@ddt.ddt
class TestXApiTransformers(XApiTransformersFixturesTestMixin, TestCase):
    """
    Test xApi event transforms and settings.
    """
    TEST_DIR_PATH = os.path.dirname(os.path.abspath(__file__))

    EVENT_FIXTURE_FILENAMES = [
        event_file_name for event_file_name in os.listdir(
            f'{TEST_DIR_PATH}/fixtures/raw/'
        ) if event_file_name.endswith(".json")
    ]

    @property
    def raw_events_fixture_path(self):
        """
        Return the path to the expected transformed events fixture files.
        """
        return f'{self.TEST_DIR_PATH}/fixtures/raw'

    @property
    def expected_events_fixture_path(self):
        """
        Return the path to the expected transformed events fixture files.
        """
        return f'{self.TEST_DIR_PATH}/fixtures/expected'

    def setUp(self):
        """
        Initialize the plugin settings.
        """
        erb_settings.plugin_settings(settings)
        common_settings.plugin_settings(settings)

        super().setUp()

    @patch('event_routing_backends.processors.xapi.transformer.get_anonymous_user_id')
    @patch('event_routing_backends.processors.xapi.transformer.get_course_from_id')
    @ddt.data(*EVENT_FIXTURE_FILENAMES)
    def test_event_transformer(self, raw_event_file_path, mock_get_course_from_id, mock_get_anonymous_user_id):
        # Generates the anonymized actor.name,
        mock_get_anonymous_user_id.return_value = UUID('32e08e30-f8ae-4ce2-94a8-c2bfe38a70cb')

        # Generates the contextActivities
        mock_get_course_from_id.return_value = {
            "display_name": "Demonstration Course",
            "id": "course-v1:edX+DemoX+Demo_Course",
        }

        # if an event's expected fixture doesn't exist, the test shouldn't fail.
        # evaluate transformation of only supported event fixtures.
        base_event_filename = os.path.basename(raw_event_file_path)

        expected_event_file_path = f'{self.expected_events_fixture_path}/{base_event_filename}'

        assert os.path.isfile(expected_event_file_path)

        self.check_event_transformer(raw_event_file_path, expected_event_file_path)
