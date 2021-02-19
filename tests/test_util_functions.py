# -*- coding: utf-8 -*-

"""
Tests for the `openedx-completion-aggregator` utils module.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime, timezone
from unittest.mock import patch

import ddt
import pytest

from django.test import TestCase

from completion_aggregator.utils import get_percent, make_datetime_timezone_unaware


@ddt.ddt
class GetPercentTestCase(TestCase):
    """
    Tests of the `get_percent` function
    """

    def test_get_percent_with_invalid_values(self):
        with pytest.raises(ValueError):
            get_percent(1.1, 0.9)

    @ddt.data(
        (0.5, 1, 0.5),
        (0.5, 2, 0.25),
    )
    @ddt.unpack
    def test_get_percent_with_valid_values(self, earned, possible, expected_percentage):
        percentage = get_percent(earned, possible)
        self.assertEqual(percentage, expected_percentage)


@ddt.ddt
class MakeTimeZoneUnawareTestCase(TestCase):
    """
    Tests of the `make_datetime_timezone_unaware` function
    """

    @ddt.data(
        (1, 10, 'a1'),
        (1, 10),
        (2, 0, 'a1'),
        (2, 2),
    )
    def test_make_datetime_timezone_unaware(self, version):
        with patch('django.VERSION', version):
            date = make_datetime_timezone_unaware(datetime.now(timezone.utc))
            assert date.tzinfo is None
