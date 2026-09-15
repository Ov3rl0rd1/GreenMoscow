from collections.abc import Sequence

from shapely.strtree import STRtree

from greenplan.domain.drawing import BlockReference, LayerGeometry
from greenplan.domain.obstacle_kinds import EXISTING_TREE, TREE_TO_REMOVE
from greenplan.domain.site import KEEP_TREE_STATUS, REMOVE_TREE_STATUS, ExistingTree
from greenplan.knowledge.layer_dictionary import LayerClassification
from greenplan.recognition.symbol_clusterer import SymbolClusterer

TREE_STATUS_BY_KIND = {EXISTING_TREE: KEEP_TREE_STATUS, TREE_TO_REMOVE: REMOVE_TREE_STATUS}


class ExistingTreeExtractor:
    def __init__(self, clusterer: SymbolClusterer, survey_coverage_radius_m: float) -> None:
        self._clusterer = clusterer
        self._survey_coverage_radius_m = survey_coverage_radius_m

    def extract(
        self,
        geometries: Sequence[LayerGeometry],
        block_references: Sequence[BlockReference],
        classifications: dict[str, LayerClassification],
    ) -> tuple[ExistingTree, ...]:
        surveyed = self._trees_from_block_references(block_references, classifications)
        drawn = self._trees_from_symbols(geometries, classifications)
        return tuple(surveyed + self._outside_survey(drawn, surveyed))

    def _trees_from_block_references(
        self, block_references: Sequence[BlockReference], classifications: dict[str, LayerClassification]
    ) -> list[ExistingTree]:
        return [
            ExistingTree(
                reference.position, TREE_STATUS_BY_KIND[kind], reference.layer, reference.source_name
            )
            for reference in block_references
            if (kind := self._tree_kind(reference.layer, classifications)) is not None
        ]

    def _trees_from_symbols(
        self, geometries: Sequence[LayerGeometry], classifications: dict[str, LayerClassification]
    ) -> list[ExistingTree]:
        trees: list[ExistingTree] = []
        for layer, source_name in {(item.layer, item.source_name) for item in geometries}:
            kind = self._tree_kind(layer, classifications)
            if kind is None:
                continue
            symbols = [
                item.geometry
                for item in geometries
                if item.layer == layer and item.source_name == source_name
            ]
            positions = self._clusterer.symbol_positions(symbols)
            trees.extend(
                ExistingTree(position, TREE_STATUS_BY_KIND[kind], layer, source_name)
                for position in positions
            )
        return trees

    def _tree_kind(self, layer: str, classifications: dict[str, LayerClassification]) -> str | None:
        classification = classifications.get(layer)
        kind = classification.kind if classification is not None else None
        return kind if kind in TREE_STATUS_BY_KIND else None

    def _outside_survey(self, drawn: list[ExistingTree], surveyed: list[ExistingTree]) -> list[ExistingTree]:
        if not surveyed:
            return drawn
        index = STRtree([tree.position for tree in surveyed])
        return [
            tree
            for tree in drawn
            if len(index.query(tree.position, predicate="dwithin", distance=self._survey_coverage_radius_m))
            == 0
        ]
