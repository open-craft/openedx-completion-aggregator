"""
Transformers for completion aggregation.
"""

from event_routing_backends.processors.openedx_filters.decorators import openedx_filter
from event_routing_backends.processors.xapi import constants
from event_routing_backends.processors.xapi.registry import XApiTransformersRegistry
from event_routing_backends.processors.xapi.transformer import XApiTransformer
from tincan import Activity, ActivityDefinition, Extensions, LanguageMap, Result, Verb


class BaseProgressTransformer(XApiTransformer):
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
        filter_type="completion_aggregator.xapi.progress.get_object",
    )
    def get_object(self) -> Activity:
        """
        Get object for xAPI transformed event.
        """
        if not self.object_type:
            raise NotImplementedError()  # pragma: no cover

        return Activity(
            id=self.get_object_iri("xblock", self.get_data("data.block_id")),
            definition=ActivityDefinition(
                type=self.object_type,
            ),
        )

    def get_result(self) -> Result:
        """
        Get result for xAPI transformed event.
        """
        progress = self.get_data("data.percent") or 0
        return Result(
            completion=progress == 1.0,
            extensions=Extensions({
                constants.XAPI_ACTIVITY_PROGRESS: (progress * 100),
            }),
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
