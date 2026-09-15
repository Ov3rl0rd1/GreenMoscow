from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.obstacle_index import ObstacleIndex
from greenplan.constraints.requirement_resolver import RequirementResolver
from greenplan.constraints.zone_builder import ZoneBuilder
from greenplan.domain.site import SiteModel
from greenplan.geometry.shapes import polygonal_parts, union_of_polygons
from greenplan.placement.planting_profile import PlantingProfile


@dataclass(frozen=True, slots=True)
class PlantingZones:
    prohibited: Polygon | MultiPolygon
    conditional: Polygon | MultiPolygon


class PlantingZoneBuilder:
    def __init__(
        self, zone_builder: ZoneBuilder, resolver: RequirementResolver, design: DesignConstraints
    ) -> None:
        self._zone_builder = zone_builder
        self._resolver = resolver
        self._design = design

    def build(
        self, site: SiteModel, profile: PlantingProfile, planned_positions: Sequence[Point]
    ) -> PlantingZones:
        area = site.plantable_surface
        if area.is_empty:
            return PlantingZones(MultiPolygon(), MultiPolygon())
        obstacles = ObstacleIndex(site.obstacles).within(area, self._search_radius_m(profile))
        normative = self._zone_builder.prohibited_zone(
            obstacles, profile.target, profile.crown_diameter_m, area
        )
        kept_trees = [tree.position for tree in site.kept_trees()]
        exclusions = _disc_parts(kept_trees, self._design.existing_tree_clearance_m(profile.target), area)
        planned = _disc_parts(planned_positions, profile.planned_plant_clearance_m, area)
        prohibited = union_of_polygons([*polygonal_parts(normative), *exclusions, *planned])
        conditional = self._zone_builder.conditional_zone(
            obstacles, profile.target, profile.crown_diameter_m, area
        )
        return PlantingZones(prohibited, conditional)

    def _search_radius_m(self, profile: PlantingProfile) -> float:
        return (
            self._resolver.max_requirement_distance_m(profile.crown_diameter_m)
            + self._design.obstacle_search_margin_m
        )


def _disc_parts(positions: Sequence[Point], radius_m: float, area: BaseGeometry) -> list[Polygon]:
    if not positions or radius_m <= 0:
        return []
    discs = shapely.buffer(np.array(positions, dtype=object), radius_m)
    return polygonal_parts(shapely.intersection(shapely.union_all(discs), area))
