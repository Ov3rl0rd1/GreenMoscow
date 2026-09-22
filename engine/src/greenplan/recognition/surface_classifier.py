from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import MultiPolygon, Polygon

from greenplan.domain.drawing import LayerGeometry
from greenplan.geometry.shapes import (
    linear_parts,
    polygon_from_closed_line,
    polygonal_parts,
    union_of_polygons,
)
from greenplan.knowledge.surface_codes import CARRIAGEWAY, LAWN, SIDEWALK, SurfaceCodeCatalog

PROJECT_SURFACES_SOURCE = "project_surfaces"
TOPOGRAPHIC_GREEN_AREAS_SOURCE = "topographic_green_areas"
NO_LAWN_SOURCE = "none"


@dataclass(frozen=True, slots=True)
class SurfaceMap:
    lawn: Polygon | MultiPolygon
    carriageway: Polygon | MultiPolygon
    sidewalk: Polygon | MultiPolygon
    lawn_source: str


class SurfaceClassifier:
    def __init__(self, catalog: SurfaceCodeCatalog) -> None:
        self._catalog = catalog

    def classify(self, geometries: Sequence[LayerGeometry]) -> SurfaceMap:
        polygons_by_class = self._project_surface_polygons(geometries)
        if polygons_by_class[LAWN]:
            return self._surface_map(polygons_by_class, PROJECT_SURFACES_SOURCE)
        polygons_by_class[LAWN] = self._topographic_green_areas(geometries)
        source = TOPOGRAPHIC_GREEN_AREAS_SOURCE if polygons_by_class[LAWN] else NO_LAWN_SOURCE
        return self._surface_map(polygons_by_class, source)

    def _project_surface_polygons(self, geometries: Sequence[LayerGeometry]) -> dict[str, list[Polygon]]:
        polygons_by_class: dict[str, list[Polygon]] = defaultdict(list)
        for item in geometries:
            surface_class = self._catalog.surface_class(item.layer)
            if surface_class is not None:
                polygons_by_class[surface_class].extend(polygonal_parts(item.geometry))
                polygons_by_class[surface_class].extend(self._closed_line_polygons(item))
        return polygons_by_class

    def _topographic_green_areas(self, geometries: Sequence[LayerGeometry]) -> list[Polygon]:
        layers = set(self._catalog.fallback_green_area_layers)
        polygons: list[Polygon] = []
        for item in geometries:
            if item.layer in layers:
                polygons.extend(polygonal_parts(item.geometry))
                polygons.extend(self._closed_line_polygons(item))
        return polygons

    def _closed_line_polygons(self, item: LayerGeometry) -> list[Polygon]:
        polygons = (polygon_from_closed_line(line) for line in linear_parts(item.geometry) if line.is_ring)
        return [polygon for polygon in polygons if polygon is not None]

    def _surface_map(self, polygons_by_class: dict[str, list[Polygon]], lawn_source: str) -> SurfaceMap:
        return SurfaceMap(
            lawn=union_of_polygons(polygons_by_class[LAWN]),
            carriageway=union_of_polygons(polygons_by_class[CARRIAGEWAY]),
            sidewalk=union_of_polygons(polygons_by_class[SIDEWALK]),
            lawn_source=lawn_source,
        )
