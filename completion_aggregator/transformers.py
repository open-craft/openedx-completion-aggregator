"""
Transformers for completion aggregation.
"""

try:
    from openedx.core.djangoapps.content.block_structure.transformer import BlockStructureTransformer
except ImportError:
    BlockStructureTransformer = object

from event_routing_backends.processors.openedx_filters.decorators import openedx_filter
from event_routing_backends.processors.xapi import constants
from event_routing_backends.processors.xapi.registry import XApiTransformersRegistry
from event_routing_backends.processors.xapi.transformer import XApiTransformer
from tincan import Activity, ActivityDefinition, LanguageMap, Result, Verb
from xblock.completable import XBlockCompletionMode


class AggregatorAnnotationTransformer(BlockStructureTransformer):
    """
    Annotate completable blocks with the aggregators which contain them.
    """

    READ_VERSION = 1
    WRITE_VERSION = 1
    AGGREGATORS = "aggregators"

    @classmethod
    def name(cls):
        """
        Return the name of the transformer.
        """
        return "completion_aggregator_annotator"

    @classmethod
    def get_block_aggregators(cls, block_structure, block_key):
        """
        Return the aggregators which contain this block.

        Arguments
        ---------
            block_structure: a BlockStructure instance
            block_key: the key of the block whose aggregators we want

        Returns
        -------
            aggregators: list or None

        """
        return block_structure.get_transformer_block_field(block_key, cls, cls.AGGREGATORS)

    @classmethod
    def collect(cls, block_structure):
        """
        Collect the data required to perform this calculation.
        """
        block_structure.request_xblock_fields("completion_mode")

    def calculate_aggregators(self, block_structure, block_key):
        """
        Calculate the set of aggregators for the specified block.
        """
        aggregators = set()
        parents = block_structure.get_parents(block_key)
        for parent in parents:
            parent_block = block_structure[parent]
            completion_mode = getattr(parent_block, 'completion_mode', XBlockCompletionMode.COMPLETABLE)
            if completion_mode == XBlockCompletionMode.EXCLUDED:
                continue
            if completion_mode == XBlockCompletionMode.AGGREGATOR:
                aggregators.add(parent)
            aggregators.update(self.get_block_aggregators(block_structure, parent))
        return aggregators

    def transform(self, usage_info, block_structure):  # pylint: disable=unused-argument
        """
        Add a field holding a list of the block's aggregators.
        """
        for block_key in block_structure.topological_traversal():
            completion_mode = block_structure.get_xblock_field(
                block_key,
                "completion_mode",
                XBlockCompletionMode.COMPLETABLE
            )
            if completion_mode != XBlockCompletionMode.EXCLUDED:
                aggregators = self.calculate_aggregators(block_structure, block_key)
                block_structure.set_transformer_block_field(block_key, self, self.AGGREGATORS, aggregators)


class BaseAggregatorXApiTransformer(XApiTransformer):
    """
    Base transformer for all completion aggregator events.
    """

    object_type = None

    def get_object(self) -> Activity:
        """
        Get object for xAPI transformed event.
        """
        if not self.object_type:
            raise NotImplementedError()

        return Activity(
            id=self.get_object_iri("xblock", self.get_data("data.block_id")),
            definition=ActivityDefinition(
                type=self.object_type,
            ),
        )


class BaseProgressTransformer(BaseAggregatorXApiTransformer):
    """
    Base transformer for completion aggregator progress events.
    """

    _verb = Verb(
        id=constants.XAPI_VERB_PROGRESSED,
        display=LanguageMap({constants.EN: constants.PROGRESSED}),
    )
    object_type = None
    additional_fields = ('result', )

    @openedx_filter(
        filter_type="completion_aggregator.xapi.base_progress.get_object",
    )
    def get_object(self) -> Activity:
        """
        Get object for xAPI transformed event.
        """
        return super().get_object()

    def get_result(self) -> Result:
        """
        Get result for xAPI transformed event.
        """
        return Result(
            completion=self.get_data("data.percent") == 1.0,
            score={
                "scaled": self.get_data("data.percent") or 0
            }
        )


@XApiTransformersRegistry.register("openedx.completion_aggregator.progress.chapter")
@XApiTransformersRegistry.register("openedx.completion_aggregator.progress.sequential")
@XApiTransformersRegistry.register("openedx.completion_aggregator.progress.vertical")
class ModuleProgressTransformer(BaseProgressTransformer):
    """
    Transformer for event generated when a user makes progress in a section, subsection or unit.
    """

    object_type = constants.XAPI_ACTIVITY_MODULE


@XApiTransformersRegistry.register("openedx.completion_aggregator.progress.course")
class CourseProgressTransformer(BaseProgressTransformer):
    """
    Transformer for event generated when a user makes progress in a course.
    """

    object_type = constants.XAPI_ACTIVITY_COURSE


class BaseCompletionTransformer(BaseAggregatorXApiTransformer):
    """
    Base transformer for aggregator completion events.
    """

    _verb = Verb(
        id=constants.XAPI_VERB_COMPLETED,
        display=LanguageMap({constants.EN: constants.COMPLETED}),
    )
    object_type = None

    @openedx_filter(
        filter_type="completion_aggregator.xapi.base_completion.get_object",
    )
    def get_object(self) -> Activity:
        """
        Get object for xAPI transformed event.
        """
        return super().get_object()


@XApiTransformersRegistry.register("openedx.completion_aggregator.completion.chapter")
@XApiTransformersRegistry.register("openedx.completion_aggregator.completion.sequential")
@XApiTransformersRegistry.register("openedx.completion_aggregator.completion.vertical")
class ModuleCompletionTransformer(BaseCompletionTransformer):
    """
    Transformer for events generated when a user completes a section, subsection or unit.
    """

    object_type = constants.XAPI_ACTIVITY_MODULE


@XApiTransformersRegistry.register("openedx.completion_aggregator.completion.course")
class CourseCompletionTransformer(BaseCompletionTransformer):
    """
    Transformer for event generated when a user completes a course.
    """

    object_type = constants.XAPI_ACTIVITY_COURSE
