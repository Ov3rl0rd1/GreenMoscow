from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from greenplan.domain.drawing import LayerGeometry
from greenplan.domain.obstacle_kinds import SITE_BOUNDARY, SURVEY_BOUNDARY
from greenplan.domain.site import BoundaryRepair
from greenplan.geometry.ring_assembler import AssembledRings, RingAssembler
from greenplan.geometry.shapes import linear_parts, polygonal_parts, union_of_polygons
from greenplan.knowledge.layer_dictionary import LayerClassification
from greenplan.recognition.settings import RecognitionSettings

WORK_BOUNDARY_SOURCE = "work_boundary"
SURVEY_BOUNDARY_SOURCE = "survey_boundary"
CONTENT_EXTENT_SOURCE = "content_extent"


@dataclass(frozen=True, slots=True)
class SiteBoundary:
    area: Polygon | MultiPolygon
    source: str
    repairs: tuple[BoundaryRepair, ...] = ()


class SiteBoundaryExtractor:
    def __init__(self, minimum_area_m2: float, assembler: RingAssembler | None = None) -> None:
        self._minimum_area_m2 = minimum_area_m2
        self._assembler = assembler or default_ring_assembler()

    def extract(
        self, geometries: Sequence[LayerGeometry], classifications: dict[str, LayerClassification]
    ) -> SiteBoundary:
        for kind, source in (
            (SITE_BOUNDARY, WORK_BOUNDARY_SOURCE),
            (SURVEY_BOUNDARY, SURVEY_BOUNDARY_SOURCE),
        ):
            assembled = self._assembled(geometries, classifications, kind)
            large = [polygon for polygon in assembled.polygons if polygon.area >= self._minimum_area_m2]
            if large:
                return SiteBoundary(union_of_polygons(large), source, assembled.repairs)
        return SiteBoundary(self._content_extent(geometries), CONTENT_EXTENT_SOURCE)

    def _assembled(
        self, geometries: Sequence[LayerGeometry], classifications: dict[str, LayerClassification], kind: str
    ) -> AssembledRings:
        items = [item for item in geometries if classifications[item.layer].kind == kind]
        rings = self._assembler.assemble([line for item in items for line in linear_parts(item.geometry)])
        areal = tuple(polygon for item in items for polygon in polygonal_parts(item.geometry))
        return AssembledRings(rings.polygons + areal, rings.repairs)

    def _content_extent(self, geometries: Sequence[LayerGeometry]) -> Polygon:
        if not geometries:
            return Polygon()
        min_x, min_y, max_x, max_y = unary_union([item.geometry for item in geometries]).bounds
        return box(min_x, min_y, max_x, max_y)


def default_ring_assembler() -> RingAssembler:
    settings = RecognitionSettings()
    return RingAssembler(
        settings.boundary_closure_tolerance_m,
        settings.boundary_contact_tolerance_m,
        settings.boundary_relative_closure_fraction,
    )
