from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point

from greenplan.domain.drawing import DrawingContent
from greenplan.domain.norms import SHRUB, TREE
from greenplan_ml.reference_conventions import (
    HEDGE_TYPE,
    MIXED_TYPE,
    PLANTED_TYPES,
    PROPOSED_STATUS,
    SHRUB_OR_TREE_TYPE,
    SHRUB_TYPE,
    TREE_TYPE,
    LayerMatch,
    ReferenceLayerConventions,
    ReferenceScheme,
)

TARGET_BY_PLANT_TYPE = {
    TREE_TYPE: TREE,
    SHRUB_TYPE: SHRUB,
    HEDGE_TYPE: SHRUB,
    SHRUB_OR_TREE_TYPE: TREE,
    MIXED_TYPE: TREE,
}
MINIMUM_SYMBOL_POINTS = 3


@dataclass(frozen=True, slots=True)
class ReferencePlanting:
    position: Point
    target: str
    plant_type: str
    species_ru: str
    layer: str
    scheme_id: str


@dataclass(frozen=True, slots=True)
class ReferencePlantings:
    plantings: tuple[ReferencePlanting, ...]
    scheme_id: str
    layer_counts: dict[str, int]

    def of_target(self, target: str) -> tuple[ReferencePlanting, ...]:
        return tuple(planting for planting in self.plantings if planting.target == target)


class ReferencePlantingExtractor:
    def __init__(self, conventions: ReferenceLayerConventions) -> None:
        self._conventions = conventions

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "ReferencePlantingExtractor":
        path = knowledge_root / "dataset" / "reference_layer_conventions.yaml"
        return cls(ReferenceLayerConventions.from_file(path))

    def extract(self, content: DrawingContent, scheme_id: str | None = None) -> ReferencePlantings:
        scheme = self._scheme_for(content, scheme_id)
        if scheme is None:
            return ReferencePlantings((), "", {})
        plantings = [
            planting
            for reference in content.block_references
            if (planting := self._from_block(reference.layer, reference.position, scheme)) is not None
        ]
        return ReferencePlantings(
            tuple(plantings),
            scheme.scheme_id,
            dict(Counter(planting.layer for planting in plantings)),
        )

    def _scheme_for(self, content: DrawingContent, scheme_id: str | None) -> ReferenceScheme | None:
        if scheme_id is not None:
            return self._conventions.scheme(scheme_id)
        return self._conventions.best_scheme(content.layer_names())

    def _from_block(self, layer: str, position: Point, scheme: ReferenceScheme) -> ReferencePlanting | None:
        match = scheme.match(layer)
        if match is None or not _is_planted(match):
            return None
        return ReferencePlanting(
            position=position,
            target=TARGET_BY_PLANT_TYPE[match.plant_type],
            plant_type=match.plant_type,
            species_ru=match.species_ru,
            layer=layer,
            scheme_id=match.scheme_id,
        )


def _is_planted(match: LayerMatch) -> bool:
    return match.status == PROPOSED_STATUS and match.plant_type in PLANTED_TYPES
