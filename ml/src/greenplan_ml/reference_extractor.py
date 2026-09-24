from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point

from greenplan.domain.drawing import DrawingContent, LayerGeometry
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
from greenplan_ml.shrub_area_fill import ShrubAreaFill

TARGET_BY_PLANT_TYPE = {
    TREE_TYPE: TREE,
    SHRUB_TYPE: SHRUB,
    HEDGE_TYPE: SHRUB,
    SHRUB_OR_TREE_TYPE: TREE,
    MIXED_TYPE: TREE,
}
MINIMUM_SYMBOL_POINTS = 3
AREA_DRAWN_TYPES = frozenset({SHRUB_TYPE, HEDGE_TYPE})


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
    def __init__(
        self, conventions: ReferenceLayerConventions, area_fill: ShrubAreaFill | None = None
    ) -> None:
        self._conventions = conventions
        self._area_fill = area_fill or ShrubAreaFill()

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
        plantings.extend(self._from_areas(content.geometries, scheme, {item.layer for item in plantings}))
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

    def _from_areas(
        self, geometries: tuple[LayerGeometry, ...], scheme: ReferenceScheme, block_layers: set[str]
    ) -> list[ReferencePlanting]:
        drawn: dict[str, list[LayerGeometry]] = defaultdict(list)
        for item in geometries:
            if item.layer not in block_layers:
                drawn[item.layer].append(item)
        plantings: list[ReferencePlanting] = []
        for layer, items in drawn.items():
            match = scheme.match(layer)
            if match is None or not _is_planted(match) or match.plant_type not in AREA_DRAWN_TYPES:
                continue
            positions = self._area_fill.positions([item.geometry for item in items])
            plantings.extend(
                ReferencePlanting(position, SHRUB, match.plant_type, match.species_ru, layer, match.scheme_id)
                for position in positions
            )
        return plantings


def _is_planted(match: LayerMatch) -> bool:
    return match.status == PROPOSED_STATUS and match.plant_type in PLANTED_TYPES
