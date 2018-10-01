"""
Blocks to be used in tests
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock


class StubCourse(XBlock):
    """
    Stub course block
    """
    completion_mode = XBlockCompletionMode.AGGREGATOR


class StubSequential(XBlock):
    """
    Stub sequential block
    """
    completion_mode = XBlockCompletionMode.AGGREGATOR


class StubHTML(XBlock):
    """
    Stub HTML block
    """
    completion_mode = XBlockCompletionMode.COMPLETABLE
