"""
Test compatibility layer that reduces dependence on edx-platform.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import itertools

import six

from completion.models import BlockCompletion


class StubCompat(object):
    """
    An AggregationUpdater with connections to edx-platform and modulestore
    replaced with local elements.
    """

    def init_course_block_key(self, modulestore, course_key):  # pylint: disable=unused-argument
        """
        Create a root usage key for the course.

        For the purposes of testing, we're just going by convention.
        """
        return course_key.make_usage_key('course', 'course')

    def init_course_blocks(self, user, course_block_key):
        """
        Not actually used in this implmentation.

        Overridden here to prevent the default behavior, which relies on
        modulestore.
        """
        pass

    def get_block_completions(self, user, course_key):
        """
        Return all completions for the current course.
        """
        return BlockCompletion.objects.filter(user=user, course_key=course_key)

    def get_children(self, course_blocks, block_key):  # pylint: disable=unused-argument
        """
        Return children for the given block.

        For the purpose of the tests, we will use the following course
        structure:

                        course
                          |
                +--+---+--^-+----+----+
               /   |   |    |    |     \
            html html html html other hidden
                                /   \
                              html hidden

        where `course` and `other` are a completion_mode of AGGREGATOR (but
        only `course` is registered to store aggregations), `html` is
        COMPLETABLE, and `hidden` is EXCLUDED.
        """
        course_key = block_key.course_key
        if block_key.block_type == 'course':
            return list(itertools.chain(
                [course_key.make_usage_key('html', 'html{}'.format(i)) for i in six.moves.range(4)],
                [course_key.make_usage_key('other', 'other')],
                [course_key.make_usage_key('hidden', 'hidden0')]
            ))
        elif block_key.block_type == 'other':
            return [
                course_key.make_usage_key('html', 'html4'),
                course_key.make_usage_key('hidden', 'hidden1')
            ]
        return []
