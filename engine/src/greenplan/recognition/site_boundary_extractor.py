from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from greenplan.domain.drawing import LayerGeometry
from greenplan.domain.obstacle_kinds import SITE_BOUNDARY, SURVEY_BOUNDARY
from greenplan.geometry.shapes import (
    linear_parts,
    polygon_from_closed_line,
    polygonal_parts,
    union_of_polygons,
)
from greenplan.knowledge.layer_dictionary import LayerClassification

WORK_BOUNDARY_SOURCE = "work_boundary"
SURVEY_BOUNDARY_SOURCE = "survey_boundary"
CONTENT_EXTENT_SOURCE = "content_extent"


@dataclass(frozen=True, slots=True)
class SiteBoundary:
    area: Polygon | MultiPolygon
    source: str


class SiteBoundaryExtractor:
    def __init__(self, minimum_area_m2: float) -> None:
        self._minimum_area_m2 = minimum_area_m2

    def extract(
        self, geometries: Sequence[LayerGeometry], classifications: dict[str, LayerClassification]
    ) -> SiteBoundary:
        for kind, source in (
            (SITE_BOUNDARY, WORK_BOUNDARY_SOURCE),
            (SURVEY_BOUNDARY, SURVEY_BOUNDARY_SOURCE),
        ):
            area = self._area_from_layers_of_kind(geometries, classifications, kind)
            if area is not None:
                return SiteBoundary(area, source)
        return SiteBoundary(self._content_extent(geometries), CONTENT_EXTENT_SOURCE)

    def _area_from_layers_of_kind(
        self, geometries: Sequence[LayerGeometry], classifications: dict[str, LayerClassification], kind: str
    ) -> Polygon | MultiPolygon | None:
        polygons = [
            polygon
            for item in geometries
            if classifications[item.layer].kind == kind
            for polygon in self._polygons_of(item)
        ]
        large = [polygon for polygon in polygons if polygon.area >= self._minimum_area_m2]
        return union_of_polygons(large) if large else None

    def _polygons_of(self, item: LayerGeometry) -> list[Polygon]:
        closed = (polygon_from_closed_line(line) for line in linear_parts(item.geometry))
        return polygonal_parts(item.geometry) + [polygon for polygon in closed if polygon is not None]

    def _content_extent(self, geometries: Sequence[LayerGeometry]) -> Polygon:
        if not geometries:
            return Polygon()
        min_x, min_y, max_x, max_y = unary_union([item.geometry for item in geometries]).bounds
        return box(min_x, min_y, max_x, max_y)
