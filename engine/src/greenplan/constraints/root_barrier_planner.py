from dataclasses import dataclass

from shapely.affinity import translate
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.domain.decisions import CONDITIONALLY_ACCEPTED, Clearance, PlantingDecision
from greenplan.domain.norms import CONDITIONAL_MEASURE, SURFACE_MEASUREMENT, Requirement
from greenplan.domain.site import Obstacle
from greenplan.geometry.shapes import linear_parts

AREAL_GEOMETRY_TYPES = frozenset({"Polygon", "MultiPolygon"})
MINIMUM_BARRIER_LENGTH_M = 0.01
REACH_CIRCLE_QUAD_SEGMENTS = 64


@dataclass(frozen=True, slots=True)
class RootBarrier:
    rule_id: str
    obstacle_kind: str
    line: LineString

    @property
    def length_m(self) -> float:
        return self.line.length


class RootBarrierPlanner:
    def __init__(self, meter: ClearanceMeter, network_to_barrier_m: float) -> None:
        self._meter = meter
        self._network_to_barrier_m = network_to_barrier_m

    def barriers(self, decision: PlantingDecision) -> tuple[RootBarrier, ...]:
        if decision.status != CONDITIONALLY_ACCEPTED:
            return ()
        trunk = decision.candidate.position
        return tuple(
            barrier
            for clearance in decision.clearances
            if needs_root_barrier(clearance)
            for barrier in self._barriers_for(trunk, clearance)
        )

    def _barriers_for(self, trunk: Point, clearance: Clearance) -> list[RootBarrier]:
        obstacle = clearance.obstacle
        requirement = clearance.requirement
        outline = outline_of(obstacle.geometry)
        axis_distance = trunk.distance(outline)
        if axis_distance <= 0:
            return []
        reach = self._meter.geometry_offset_m(obstacle, requirement)
        stretch = outline.intersection(trunk.buffer(reach, quad_segs=REACH_CIRCLE_QUAD_SEGMENTS))
        anchor = nearest_points(outline, trunk)[0]
        shift = min(
            self._surface_offset_m(obstacle, requirement) + self._network_to_barrier_m,
            axis_distance - self._meter.trunk_radius_m(),
        )
        step_x = (trunk.x - anchor.x) / axis_distance * shift
        step_y = (trunk.y - anchor.y) / axis_distance * shift
        return [
            RootBarrier(requirement.rule_id, obstacle.kind, translate(part, step_x, step_y))
            for part in linear_parts(stretch)
            if part.length >= MINIMUM_BARRIER_LENGTH_M
        ]

    def _surface_offset_m(self, obstacle: Obstacle, requirement: Requirement) -> float:
        offset = self._meter.geometry_offset_m(obstacle, requirement) - requirement.distance_m
        if requirement.measurement_mode == SURFACE_MEASUREMENT:
            return offset - self._meter.trunk_radius_m()
        return offset


def needs_root_barrier(clearance: Clearance) -> bool:
    return not clearance.satisfied and clearance.requirement.severity == CONDITIONAL_MEASURE


def outline_of(geometry: BaseGeometry) -> BaseGeometry:
    return geometry.boundary if geometry.geom_type in AREAL_GEOMETRY_TYPES else geometry


def total_length_m(barriers: tuple[RootBarrier, ...]) -> float:
    return sum(barrier.length_m for barrier in barriers)
