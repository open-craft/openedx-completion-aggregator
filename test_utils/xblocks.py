"""
XBlock types for use in completion tests
"""

from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock


class CourseBlock(XBlock):
    """
    A registered aggregator block.
    """
    completion_mode = XBlockCompletionMode.AGGREGATOR


class HTMLBlock(XBlock):
    """
    A completable block.
    """
    completion_mode = XBlockCompletionMode.COMPLETABLE


class HiddenBlock(XBlock):
    """
    An excluded block.
    """
    completion_mode = XBlockCompletionMode.EXCLUDED


class OtherAggBlock(XBlock):
    """
    An unregistered aggregator block.
    """
    completion_mode = XBlockCompletionMode.AGGREGATOR


class InvalidModeBlock(XBlock):
    """
    A block with an invalid value for completion mode.
    """
    completion_mode = 'not-a-completion-mode'
