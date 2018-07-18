"""
Serializers for the Completion API.
"""

# pylint: disable=abstract-method

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
from collections import defaultdict

import six
from rest_framework import serializers
from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock
from xblock.plugin import PluginMissingError

from django.db import transaction

from . import compat
from .models import Aggregator, StaleCompletion
from .tasks.aggregation_tasks import AggregationUpdater

log = logging.getLogger(__name__)


def get_completion_mode(block):
    """
    Return the completion_mode of the specified block.

    Blocks with no explicit completion_mode are considered to be
    COMPLETABLE.
    """
    return getattr(block, "completion_mode", XBlockCompletionMode.COMPLETABLE)


def is_aggregation_name(category):
    """
    Return True if the named category is a valid aggregation name.

    Currently, valid aggregators comprise the list of block types that have
    a completion_mode of XBlockCompletionMode.AGGREGATOR, but this may be
    expanded in the future.
    """
    try:
        cls = XBlock.load_class(category)
    except PluginMissingError:
        return False

    return get_completion_mode(cls) == XBlockCompletionMode.AGGREGATOR


class AggregatorAdapter(object):
    """
    Adapter for presenting Aggregators to the serializer.

    Can be given a collection of Aggregator objects, or a single Aggregator
    at a time, that all belong to the same user and course

    By default, stale completions are not recalculated, and the given aggregators
    are used as provided.  To detect stale completions and force them to be
    recalculated, pass `recalculate_stale=True`.

    Usage:

    To create AggregatorAdapters for a user's courses with a given queryset:

        >>> from completion_aggregator.models import Aggregator
        >>> from completion_aggregator.serializers import AggregatorAdapter
        >>> aggregators = Aggregator.objects.filter(
        >>>     user=user,
        >>>     aggregation_name__in=['course', 'chapter', 'vertical']
        >>> )
        >>> adapters = []
        >>> for course_key in Enrollments.objects.filter(user=user, active=True):
        >>>     adapters.append(AggregatorAdapter(
        >>>         user=user,
        >>>         course_key=course_key,
        >>>         aggregators=aggregators,
        >>>     ))

    To add an aggregator or iterable of aggregators to an adapter:

        >>> from completion_aggregator.serializers import AggregatorAdapter
        >>> adapter = AggregatorAdapter(
        >>>     user=user,
        >>>     course_key=course_key,
        >>> )
        >>> adapter.add_aggregate_completion(completion1)
        >>> adapter.update_aggregators([completion2, completion3])

    The adapter or list of adapters can then be passed to the serializer for processing.
    """

    def __init__(self, user, course_key, aggregators=None, recalculate_stale=False):
        """
        Initialize the adapter.

        Optionally, an initial collection of aggregators may be provided, though these may be recalculated if the course
        is found to have stale completions.
        """
        self.user = user
        self.course_key = course_key
        self.aggregators = defaultdict(list)

        # If requested, check for stale completions, to trigger recalculating the aggregators if any are found.
        is_stale = False
        if recalculate_stale:
            with transaction.atomic():
                stale_completions = [
                    stale.id for stale in StaleCompletion.objects.select_for_update().filter(
                        resolved=False,
                        username=self.user.username,
                        course_key=self.course_key,
                    )
                ]
                is_stale = bool(stale_completions)

                if is_stale:
                    log.info("Resolving %s stale completions for %s+%s",
                             len(stale_completions), self.user.username, self.course_key)
                    StaleCompletion.objects.filter(id__in=stale_completions).update(resolved=True)

        self.update_aggregators(aggregators or [], is_stale)

    def __getattr__(self, name):
        """
        Provide the serializer with access to custom aggregators.
        """
        if is_aggregation_name(name):
            return self.aggregators.get(name, [])
        else:
            raise AttributeError

    def add_aggregator(self, aggregator):
        """
        Add an aggregator to the AggregatorAdapter.

        When adding, check whether it meets the criteria for user, course_key,
        and aggregation_name
        """
        if (aggregator.user, aggregator.course_key) != (self.user, self.course_key):
            raise ValueError("AggregatorAdapter received Aggregator for the wrong enrollment.")
        if is_aggregation_name(aggregator.aggregation_name):
            self.aggregators[aggregator.aggregation_name].append(aggregator)

    def update_aggregators(self, iterable, is_stale=False):
        """
        Add a number of Aggregators to the adapter.

        If stale completions are flagged, then recalculate and use the updated aggregations instead.
        """
        if is_stale:
            log.info("Stale completions found for %s+%s, recalculating.", self.user, self.course_key)
            updater = AggregationUpdater(self.user, self.course_key, compat.get_modulestore())
            updater.update()
            iterable = updater.aggregators.values()

        for aggregator in iterable:
            self.add_aggregator(aggregator)

    @property
    def course(self):
        """
        Return the Aggregator for the course as a whole.

        If no course completion exists, use a dummy completion
        """
        if self.aggregators['course']:
            return self.aggregators['course'][0]
        return Aggregator(
            user=self.user,
            course_key=self.course_key,
            aggregation_name='course',
            earned=0.0,
            possible=None,
            percent=None,
        )

    @property
    def earned(self):
        """
        Report the number of earned completions for the course.

        Returns a positive float.
        """
        return self.course.earned

    @property
    def possible(self):
        """
        Report the number of possible completions for the course.

        Returns a positive float.
        """
        return self.course.possible

    @property
    def percent(self):
        """
        Report the percentage of possible completions earned.
        """
        return self.course.percent


class _CompletionSerializer(serializers.Serializer):
    """
    Inner serializer for actual completion data.
    """

    earned = serializers.FloatField()
    possible = serializers.FloatField()
    percent = serializers.FloatField()


class _CompletionSerializerV0(_CompletionSerializer):
    """
    Completion Serializer for V0 API (includes ratio field).
    """

    ratio = serializers.SerializerMethodField()

    def get_ratio(self, obj):
        """
        Return ratio based on percent.
        """
        return obj.percent


class CourseCompletionSerializer(serializers.Serializer):
    """
    Serialize completions at the course level.
    """

    course_key = serializers.CharField()
    completion = _CompletionSerializer(source='*')
    username = serializers.SerializerMethodField()
    mean = serializers.FloatField()

    optional_fields = {'mean', 'username'}

    def __init__(self, instance, requested_fields=frozenset(), *args, **kwargs):
        """
        Initialize a course completion serializer.

        Add any requested optional fields.
        """
        super(CourseCompletionSerializer, self).__init__(instance, *args, **kwargs)
        for field in self.optional_fields - requested_fields:
            del self.fields[field]

    def get_username(self, obj):
        """
        Serialize the username.
        """
        return obj.user.username


class CourseCompletionSerializerV0(CourseCompletionSerializer):
    """
    Serializer for V0 API (to include ratio field).
    """

    completion = _CompletionSerializerV0(source='*')


class BlockCompletionSerializer(serializers.Serializer):
    """
    A serializer that represents aggregators of sub-graphs of xblocks.
    """

    course_key = serializers.CharField()
    block_key = serializers.CharField()
    completion = _CompletionSerializer(source='*')


class BlockCompletionSerializerV0(BlockCompletionSerializer):
    """
    A serializer that represents aggregators of sub-graphs of xblocks.
    """

    completion = _CompletionSerializerV0(source='*')


def course_completion_serializer_factory(requested_fields, version=1):
    """
    Configure and create a serializer for aggregators.

    The created serializer nests appropriate
    BlockCompletionSerializers for the specified requested_fields.
    """
    if version == 0:
        course_completion_serializer = CourseCompletionSerializerV0
        block_completion_serializer = BlockCompletionSerializerV0
    else:
        course_completion_serializer = CourseCompletionSerializer
        block_completion_serializer = BlockCompletionSerializer
    dunder_dict = {
        field: block_completion_serializer(many=True) for field in requested_fields
        if is_aggregation_name(field)
    }
    return type(
        native_identifier('CourseCompletionSerializerWithAggregators'),
        (course_completion_serializer,),
        dunder_dict,
    )


def native_identifier(string):
    """
    Convert identifiers to the native str type.

    This is required for the first argument to three-argument-`type()`.  This
    function expects all identifiers comprise only ascii characters.
    """
    if six.PY2:  # pragma: no cover

        if isinstance(string, six.text_type):
            # Python 2 identifiers are required to be ascii
            string = string.encode('ascii')
    elif isinstance(string, bytes):  # pragma: no cover
        # Python 3 identifiers can technically be non-ascii, but don't do that.
        string = string.decode('ascii')
    return string
