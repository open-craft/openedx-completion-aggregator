"""
Various utility functionality.
"""

from django.contrib.auth import get_user_model


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
