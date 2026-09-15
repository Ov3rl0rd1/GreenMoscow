from dataclasses import dataclass

from shapely.geometry import Point

from greenplan.domain.norms import STRUCTURE_EDGE_MEASUREMENT, SURFACE_MEASUREMENT, NormsDefaults, Requirement
from greenplan.domain.obstacle_kinds import HEATING_NETWORK
from greenplan.domain.site import Obstacle


@dataclass(frozen=True, slots=True)
class MeasuredClearance:
    actual_m: float
    assumed_outer_radius: bool


class ClearanceMeter:
    def __init__(self, defaults: NormsDefaults) -> None:
        self._defaults = defaults

    def measure(self, position: Point, obstacle: Obstacle, requirement: Requirement) -> MeasuredClearance:
        axis_distance = position.distance(obstacle.geometry)
        offset, assumed = self._offset(obstacle, requirement)
        return MeasuredClearance(axis_distance - offset, assumed)

    def geometry_offset_m(self, obstacle: Obstacle, requirement: Requirement) -> float:
        offset, _assumed = self._offset(obstacle, requirement)
        return requirement.distance_m + offset

    def trunk_radius_m(self) -> float:
        return self._defaults.trunk_diameter_at_planting_m / 2

    def _offset(self, obstacle: Obstacle, requirement: Requirement) -> tuple[float, bool]:
        if requirement.measurement_mode == SURFACE_MEASUREMENT:
            radius, assumed = self._outer_radius(obstacle)
            return radius + self.trunk_radius_m(), assumed
        if requirement.measurement_mode == STRUCTURE_EDGE_MEASUREMENT:
            return self._outer_radius(obstacle)
        return 0.0, False

    def _outer_radius(self, obstacle: Obstacle) -> tuple[float, bool]:
        if obstacle.outer_radius_m is not None:
            return obstacle.outer_radius_m, False
        if obstacle.kind == HEATING_NETWORK:
            return self._defaults.unknown_heating_channel_width_m / 2, True
        return self._defaults.unknown_pipe_outer_diameter_m / 2, True
