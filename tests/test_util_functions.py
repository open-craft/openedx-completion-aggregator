# -*- coding: utf-8 -*-

"""
Tests for the `openedx-completion-aggregator` utils module.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import ddt
import pytest

from django.test import TestCase

from completion_aggregator.utils import get_percent


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
