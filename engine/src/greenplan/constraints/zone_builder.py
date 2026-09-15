from collections.abc import Iterable, Sequence

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.constraints.requirement_resolver import RequirementResolver
from greenplan.domain.norms import CONDITIONAL, CONDITIONAL_MEASURE, PROHIBITIVE
from greenplan.domain.site import Obstacle
from greenplan.geometry.shapes import polygonal_parts, union_of_polygons

BUFFER_QUADRANT_SEGMENTS = 8
CONDITIONAL_SEVERITIES = frozenset({CONDITIONAL, CONDITIONAL_MEASURE})


class ZoneBuilder:
    def __init__(self, resolver: RequirementResolver, meter: ClearanceMeter) -> None:
        self._resolver = resolver
        self._meter = meter

    def prohibited_zone(
        self, obstacles: Sequence[Obstacle], target: str, crown_diameter_m: float, area: BaseGeometry
    ) -> Polygon | MultiPolygon:
        return self._zone(obstacles, target, crown_diameter_m, area, frozenset({PROHIBITIVE}))

    def conditional_zone(
        self, obstacles: Sequence[Obstacle], target: str, crown_diameter_m: float, area: BaseGeometry
    ) -> Polygon | MultiPolygon:
        return self._zone(obstacles, target, crown_diameter_m, area, CONDITIONAL_SEVERITIES)

    def _zone(
        self,
        obstacles: Sequence[Obstacle],
        target: str,
        crown_diameter_m: float,
        area: BaseGeometry,
        severities: frozenset[str],
    ) -> Polygon | MultiPolygon:
        geometries, offsets = self._buffer_inputs(obstacles, target, crown_diameter_m, severities)
        if not geometries:
            return MultiPolygon()
        buffers = shapely.buffer(geometries, offsets, quad_segs=BUFFER_QUADRANT_SEGMENTS)
        clipped = shapely.intersection(shapely.union_all(buffers), area)
        return union_of_polygons(polygonal_parts(clipped))

    def _buffer_inputs(
        self, obstacles: Iterable[Obstacle], target: str, crown_diameter_m: float, severities: frozenset[str]
    ) -> tuple[list[BaseGeometry], list[float]]:
        geometries: list[BaseGeometry] = []
        offsets: list[float] = []
        for obstacle in obstacles:
            offset = self._largest_offset(obstacle, target, crown_diameter_m, severities)
            if offset > 0:
                geometries.append(obstacle.geometry)
                offsets.append(offset)
        return geometries, offsets

    def _largest_offset(
        self, obstacle: Obstacle, target: str, crown_diameter_m: float, severities: frozenset[str]
    ) -> float:
        requirements = self._resolver.resolve(obstacle.kind, target, crown_diameter_m)
        offsets = [
            self._meter.geometry_offset_m(obstacle, requirement)
            for requirement in requirements
            if requirement.severity in severities
        ]
        return max(offsets, default=0.0)
