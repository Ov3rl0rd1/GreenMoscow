from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from greenplan.domain.obstacle_kinds import (
    BUILDING_WALL,
    BUS_SHELTER,
    CARRIAGEWAY_EDGE,
    HEATING_NETWORK,
    OVERHEAD_LINE,
)
from greenplan.domain.site import SiteModel
from greenplan.species.species_settings import SpeciesSettings

STREET_CARRIAGEWAY_ADJACENT = "street_carriageway_adjacent"
NEAR_HEATING_NETWORK = "near_heating_network"
BUS_STOP = "bus_stop"
UNDER_OVERHEAD_LINE = "under_overhead_line"
NEAR_BUILDING = "near_building"


@dataclass(frozen=True, slots=True)
class PlantingContext:
    carriageway_distance_m: float
    heating_axis_distance_m: float
    bus_shelter_distance_m: float
    overhead_line_distance_m: float
    tags: frozenset[str]
    building_distance_m: float = float("inf")


class _NearestGeometry:
    def __init__(self, geometries: Sequence[BaseGeometry]) -> None:
        self._geometries = list(geometries)
        self._tree = STRtree(self._geometries) if self._geometries else None

    def distance_m(self, point: Point) -> float:
        if self._tree is None:
            return float("inf")
        return self._geometries[int(self._tree.nearest(point))].distance(point)


class SiteContextDetector:
    def __init__(self, site: SiteModel, settings: SpeciesSettings) -> None:
        self._settings = settings
        self._carriageway = _nearest_of(site, CARRIAGEWAY_EDGE)
        self._heating = _nearest_of(site, HEATING_NETWORK)
        self._shelters = _nearest_of(site, BUS_SHELTER)
        self._overhead_lines = _nearest_of(site, OVERHEAD_LINE)
        self._buildings = _nearest_of(site, BUILDING_WALL)

    def detect(self, position: Point) -> PlantingContext:
        distances = (
            self._carriageway.distance_m(position),
            self._heating.distance_m(position),
            self._shelters.distance_m(position),
            self._overhead_lines.distance_m(position),
        )
        building = self._buildings.distance_m(position)
        tags = self._tags(*distances, building)
        return PlantingContext(*distances, tags=tags, building_distance_m=building)

    def _tags(
        self, carriageway: float, heating: float, shelter: float, overhead: float, building: float
    ) -> frozenset[str]:
        settings = self._settings
        thresholds = (
            (STREET_CARRIAGEWAY_ADJACENT, carriageway, settings.carriageway_context_distance_m),
            (NEAR_HEATING_NETWORK, heating, settings.heating_context_distance_m),
            (BUS_STOP, shelter, settings.bus_stop_context_distance_m),
            (UNDER_OVERHEAD_LINE, overhead, settings.overhead_line_context_distance_m),
            (NEAR_BUILDING, building, settings.building_context_distance_m),
        )
        return frozenset(tag for tag, distance, limit in thresholds if distance <= limit)


def _nearest_of(site: SiteModel, kind: str) -> _NearestGeometry:
    return _NearestGeometry([obstacle.geometry for obstacle in site.obstacles_of(kind)])
