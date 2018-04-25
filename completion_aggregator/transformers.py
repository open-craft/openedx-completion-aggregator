"""
Transformers for completion aggregation.
"""

try:
    from openedx.core.djangoapps.content.block_structure.transformer import BlockStructureTransformer
except ImportError:
    BlockStructureTransformer = object

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

        Arguments:
            block_structure: a BlockStructure instance
            block_key: the key of the block whose aggregators we want
        Returns:
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
            elif completion_mode == XBlockCompletionMode.AGGREGATOR:
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
