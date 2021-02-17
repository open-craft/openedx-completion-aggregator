"""
Various utility functionality.
"""
import django
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import ugettext as _

WAFFLE_AGGREGATE_STALE_FROM_SCRATCH = 'completion_aggregator.aggregate_stale_from_scratch'


class BagOfHolding(object):
    """
    A container that contains everything.
    """

    def __contains__(self, value):
        """
        Return True, because the object is already contained.
        """
        return True

    def add(self, value):
        """
        Ignore attempts to add objects to the BagOfHolding.
        """
        pass


def get_active_users(course_key):
    """
    Return a list of users that have Aggregators in the course.
    """
    return get_user_model().objects.filter(aggregator__course_key=course_key).distinct()


def make_datetime_timezone_unaware(date):
    """
    Return a timezone unaware(localize) version of the datetime instance.
    """
    # pylint: disable=line-too-long
    # Ref: https://github.com/django/django/commit/e707e4c709c2e3f2dad69643eb838f87491891f8#diff-af003fcfed7cfbdeb396f8647ed0f92fR258
    # pylint: enable=line-too-long
    if django.VERSION >= (1, 10):
        date = date.astimezone(timezone.utc).replace(tzinfo=None)
    return date


def get_percent(earned, possible):
    """
    Return percentage completion value on the basis of earned and possible.
    """
    if earned > possible:
        raise ValueError(_('Earned cannot be greater than the possible value.'))
    if possible > 0.0:
        percent = earned / possible
    else:
        percent = 1.0
    return percent
