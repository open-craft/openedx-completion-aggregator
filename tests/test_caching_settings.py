"""
Tests for the caching and performance settings.

Tests for:
- COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT
- COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE
"""

import mock
from opaque_keys.edx.keys import CourseKey

from django.test import TestCase, override_settings

from completion_aggregator import compat


class CollectedBlockStructureTestCase(TestCase):
    """
    Test the collected block structure feature.
    """

    def test_feature_disabled_by_default(self):
        """
        Test that collected block structure is not fetched when disabled (default).
        """
        course_key = CourseKey.from_string('course-v1:edx+test+2024')
        result = compat.get_collected_block_structure(course_key)
        assert result is None

    @override_settings(COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE=True)
    def test_feature_enabled_returns_cached_structure(self):
        """
        Test that collected block structure is fetched when enabled.
        """
        course_key = CourseKey.from_string('course-v1:edx+test+2024')
        mock_block_structure = mock.MagicMock()

        # Create a mock BlockStructureNotFound exception class
        mock_exceptions = mock.MagicMock()
        mock_exceptions.BlockStructureNotFound = type('BlockStructureNotFound', (Exception,), {})

        # Mock the imports inside get_collected_block_structure
        with mock.patch.dict('sys.modules', {
            'openedx': mock.MagicMock(),
            'openedx.core': mock.MagicMock(),
            'openedx.core.djangoapps': mock.MagicMock(),
            'openedx.core.djangoapps.content': mock.MagicMock(),
            'openedx.core.djangoapps.content.block_structure': mock.MagicMock(),
            'openedx.core.djangoapps.content.block_structure.api': mock.MagicMock(),
            'openedx.core.djangoapps.content.block_structure.exceptions': mock_exceptions,
        }):
            with mock.patch(
                'openedx.core.djangoapps.content.block_structure.api.get_course_in_cache',
                return_value=mock_block_structure
            ) as mock_get_cache:
                # Force reimport to pick up the mock
                import importlib
                importlib.reload(compat)
                result = compat.get_collected_block_structure(course_key)
                mock_get_cache.assert_called_once_with(course_key)
                assert result is mock_block_structure

    @override_settings(COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE=True)
    def test_feature_enabled_handles_block_structure_not_found(self):
        """
        Test that BlockStructureNotFound is handled gracefully (cache miss).
        """
        course_key = CourseKey.from_string('course-v1:edx+test+2024')

        # Create real exception class for the test
        class BlockStructureNotFound(Exception):
            pass

        mock_exceptions = mock.MagicMock()
        mock_exceptions.BlockStructureNotFound = BlockStructureNotFound

        mock_api = mock.MagicMock()
        mock_api.get_course_in_cache.side_effect = BlockStructureNotFound("Cache miss")

        with mock.patch.dict('sys.modules', {
            'openedx': mock.MagicMock(),
            'openedx.core': mock.MagicMock(),
            'openedx.core.djangoapps': mock.MagicMock(),
            'openedx.core.djangoapps.content': mock.MagicMock(),
            'openedx.core.djangoapps.content.block_structure': mock.MagicMock(),
            'openedx.core.djangoapps.content.block_structure.api': mock_api,
            'openedx.core.djangoapps.content.block_structure.exceptions': mock_exceptions,
        }):
            import importlib
            importlib.reload(compat)
            result = compat.get_collected_block_structure(course_key)
            # Should return None gracefully
            assert result is None
