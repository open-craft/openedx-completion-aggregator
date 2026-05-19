"""
Tests for the caching and performance settings.

Tests for:
- COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT
- COMPLETION_AGGREGATOR_USE_COLLECTED_BLOCK_STRUCTURE
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import mock
from opaque_keys.edx.keys import CourseKey

from django.conf import settings
from django.test import TestCase, override_settings

from completion_aggregator import compat
from completion_aggregator.core import UpdaterCache


class UpdaterCacheTimeoutTestCase(TestCase):
    """
    Test that the UpdaterCache timeout is configurable.
    """

    def test_default_timeout(self):
        """
        Test that the default timeout is 600 seconds (10 minutes).
        """
        assert settings.COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT == 600

    @override_settings(COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT=7200)
    def test_cache_set_uses_configured_timeout(self):
        """
        Test that UpdaterCache.set() uses the configured timeout.
        """
        course_key = CourseKey.from_string('course-v1:edx+test+2024')
        cache = UpdaterCache(user_id=1, course_key=course_key, root_block=None)

        with mock.patch('completion_aggregator.core.CacheGroup') as mock_cache_group:
            mock_instance = mock_cache_group.return_value
            cache.set({'test': 'value'})
            mock_instance.set.assert_called_once_with(
                str(course_key),
                cache.cache_key,
                {'test': 'value'},
                timeout=7200
            )

    @override_settings(COMPLETION_AGGREGATOR_UPDATER_CACHE_TIMEOUT=1800)
    def test_cache_touch_uses_configured_timeout(self):
        """
        Test that UpdaterCache.touch() uses the configured timeout.
        """
        course_key = CourseKey.from_string('course-v1:edx+test+2024')
        cache = UpdaterCache(user_id=1, course_key=course_key, root_block=None)

        with mock.patch('completion_aggregator.core.CacheGroup') as mock_cache_group:
            mock_instance = mock_cache_group.return_value
            cache.touch()
            mock_instance.touch.assert_called_once_with(cache.cache_key, timeout=1800)


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
