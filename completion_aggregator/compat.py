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


def get_item_not_found_error():
    """
    Return ItemNotFoundError.
    """
    from xmodule.modulestore.exceptions import ItemNotFoundError  # pylint: disable=import-error
    return ItemNotFoundError


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


def get_users_enrolled_in(course_key):
    """
    Return list of users enrolled in supplied course_key.
    """
    return course_enrollment_model().objects.users_enrolled_in(course_key)


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


def get_mobile_only_courses(enrollments):
    """
    Return list of courses with mobile available given a list of enrollments.
    """
    from openedx.core.djangoapps.content.course_overviews.models import CourseOverview  # pylint: disable=import-error
    course_keys = []
    for course_enrollment in enrollments:
        course_keys.append(course_enrollment.course_id)
    course_overview_list = CourseOverview.objects.filter(id__in=course_keys, mobile_available=True)
    filtered_course_overview = [overview.id for overview in course_overview_list]
    return enrollments.filter(course_id__in=filtered_course_overview)


def get_course(course_key):
    """
    Get course for given key.
    """
    from courseware.courses import _get_course  # pylint: disable=import-error
    return _get_course(course_key)
