"""
Code used to interface with edx-platform.

This needs to be stubbed out for tests.  If a module, `caller` calls:

    from completion_aggregator import compat,

It can be stubbed out using:

    import test_utils.compat
    mock.patch('caller.compat', test_utils.compat.StubCompat(list_of_usage_keys))

`StubCompat` is a class which implements all the below methods in a way that
eliminates external dependencies
"""
from __future__ import absolute_import, unicode_literals

from django.conf import settings

from .transformers import AggregatorAnnotationTransformer


def get_aggregated_model():
    """
    Return a string naming the model that we are aggregating.

    Normally, this will be 'completion.BlockCompletion', but tests will need to
    override it to avoid hooking into edx-platform.
    """
    return getattr(settings, 'COMPLETION_AGGREGATED_MODEL_OVERRIDE', 'completion.BlockCompletion')


def init_course_block_key(modulestore, course_key):
    """
    Return a UsageKey for the root course block.
    """
    # pragma: no-cover
    return modulestore.make_course_usage_key(course_key)


def get_modulestore():
    """
    Return an instance of the modulestore.
    """
    from xmodule.modulestore.django import modulestore   # pylint: disable=import-error
    return modulestore()


def init_course_blocks(user, course_block_key):
    """
    Return a BlockStructure representing the course.

    Blocks must have the following attributes:

        .location
        .block_type
    """
    # pragma: no-cover
    from lms.djangoapps.course_blocks.api import get_course_block_access_transformers, get_course_blocks  # pylint: disable=import-error
    from openedx.core.djangoapps.content.block_structure.transformers import BlockStructureTransformers  # pylint: disable=import-error

    transformers = BlockStructureTransformers(
        get_course_block_access_transformers() + [AggregatorAnnotationTransformer()]
    )

    return get_course_blocks(user, course_block_key, transformers)


def get_block_completions(user, course_key):
    """
    Return the list of BlockCompletions.

    Each must have the following attributes:

        .block_key (UsageKey)
        .modified (datetime)
        .completion (float in range [0.0, 1.0])
    """
    from completion.models import BlockCompletion
    return BlockCompletion.objects.filter(
        user=user,
        course_key=course_key,
    )


def get_children(course_blocks, block_key):
    """
    Return a list of blocks that are direct children of the specified block.

    ``course_blocks`` is not imported here, but it is hard to replicate
    without access to edx-platform, so tests will want to stub it out.
    """
    return course_blocks.get_children(block_key)


def course_enrollment_model():
    """
    Return the student.models.CourseEnrollment model.
    """
    # pragma: no-cover
    from student.models import CourseEnrollment  # pylint: disable=import-error
    return CourseEnrollment


def get_affected_aggregators(course_blocks, changed_blocks):
    """
    Return the set of aggregator blocks that may need updating.
    """
    affected_aggregators = set()
    for block in changed_blocks:
        block_aggregators = course_blocks.get_transformer_block_field(
            block,
            AggregatorAnnotationTransformer,
            AggregatorAnnotationTransformer.AGGREGATORS
        )
        affected_aggregators.update(block_aggregators)
    return affected_aggregators
