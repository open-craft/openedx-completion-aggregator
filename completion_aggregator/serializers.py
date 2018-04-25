"""
Serializers for the Completion API.
"""

# pylint: disable=abstract-method

from __future__ import absolute_import, division, print_function, unicode_literals

from collections import defaultdict

import six
from rest_framework import serializers
from xblock.completable import XBlockCompletionMode
from xblock.core import XBlock
from xblock.plugin import PluginMissingError

from .models import Aggregator


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
    at a time.  The adapter automatically filters out objects that do not
    belong to the given user and course, or that pertain to aggregations that
    we are not interested in.  This is done to facilitate working with
    querysets that take in objects from multiple courses (or for multiple
    users) all at once.

    Usage:

    To create AggregatorAdapters for a user's courses with a given queryset:

        >>> from completion_aggregator.models import Aggregator
        >>> from completion_aggregator.serializers import AggregatorAdapter
        >>> completions = Aggregator.objects.filter(
        >>>     user=user,
        >>>     aggregation_name__in=['course', 'chapter', 'vertical']
        >>> )
        >>> adapters = []
        >>> for course_key in Enrollments.objects.filter(user=user, active=True):
        >>>     adapters.append(AggregatorAdapter(
        >>>         user=user,
        >>>         course_key=course_key,
        >>>         queryset=completions,
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

    def __init__(self, user, course_key, queryset=None):
        """
        Initialize the adapter.

        Optionally, an initial collection of aggregators may be provided.
        """
        self.user = user
        self.course_key = course_key
        self.aggregators = defaultdict(list)
        if queryset:
            self.update_aggregators(queryset)

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
        if (aggregator.user, aggregator.course_key) == (self.user, self.course_key):
            if is_aggregation_name(aggregator.aggregation_name):
                self.aggregators[aggregator.aggregation_name].append(aggregator)

    def update_aggregators(self, iterable):
        """
        Add a number of Aggregators to the adapter.
        """
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

        Returns a float in the range [0.0, 1.0], where 1.0 == 100%.
        """
        return self.course.percent


class _CompletionSerializer(serializers.Serializer):
    """
    Inner serializer for actual completion data.
    """

    earned = serializers.FloatField()
    possible = serializers.FloatField()
    percent = serializers.FloatField()


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


class BlockCompletionSerializer(serializers.Serializer):
    """
    A serializer that represents aggregators of sub-graphs of xblocks.
    """

    course_key = serializers.CharField()
    block_key = serializers.CharField()
    completion = _CompletionSerializer(source='*')


def course_completion_serializer_factory(requested_fields):
    """
    Configure and create a serializer for aggregators.

    The created serializer nests appropriate
    BlockCompletionSerializers for the specified requested_fields.
    """
    dunder_dict = {
        field: BlockCompletionSerializer(many=True) for field in requested_fields
        if is_aggregation_name(field)
    }
    return type(
        native_identifier('CourseCompletionSerializerWithAggregators'),
        (CourseCompletionSerializer,),
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
