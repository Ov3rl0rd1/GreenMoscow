import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from greenplan.domain.errors import ConfigurationError
from greenplan.domain.site import SiteModel
from greenplan.geometry.shapes import polygonal_parts
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.placement.placement_settings import PlacementSettings

PER_KILOMETER = "1 км"
PER_HECTARE = "1 га"
OTHER_CONTEXT = "other"
UPPER_BOUND = "upper"
LOWER_BOUND = "lower"
METERS_IN_KILOMETER = 1000.0
SQUARE_METERS_IN_HECTARE = 10_000.0


@dataclass(frozen=True, slots=True)
class SpacingBounds:
    tree: str | None = None
    shrub: str | None = None


@dataclass(frozen=True, slots=True)
class PlantingLimits:
    tree_spacing_m: float
    shrub_spacing_m: float
    max_trees: int
    max_shrubs: int
    density_measure: float
    density_unit: str
    rule_ids: tuple[str, ...]


class PlantingLimitsResolver:
    def __init__(self, repository: NormsRepository, settings: PlacementSettings) -> None:
        self._repository = repository
        self._settings = settings

    def resolve(self, site: SiteModel, bounds: SpacingBounds | None = None) -> PlantingLimits:
        settings = self._settings
        sides = bounds or SpacingBounds()
        spacing = self._repository.rule(settings.spacing_rule_id).parameters["spacing_m"]
        density = self._repository.rule(settings.density_rule_id).parameters
        unit = _density_unit(density["per"], settings.density_context)
        measure = _density_measure(site, unit, settings.street_piece_gap_m)
        caps = density["max_count"][settings.density_context]
        return PlantingLimits(
            tree_spacing_m=bound_of(spacing[settings.tree_spacing_key], sides.tree or settings.range_bound),
            shrub_spacing_m=bound_of(
                spacing[settings.shrub_spacing_key], sides.shrub or settings.range_bound
            ),
            max_trees=math.floor(bound_of(caps["trees"], settings.range_bound) * measure),
            max_shrubs=math.floor(bound_of(caps["shrubs"], settings.range_bound) * measure),
            density_measure=measure,
            density_unit=unit,
            rule_ids=(settings.spacing_rule_id, settings.density_rule_id),
        )


def bound_of(value: Any, side: str) -> float:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return float(value[-1] if side == UPPER_BOUND else value[0])
    return float(value)


def _density_unit(per: Mapping[str, str], context: str) -> str:
    return per.get(context, per[OTHER_CONTEXT])


def _density_measure(site: SiteModel, unit: str, piece_gap_m: float) -> float:
    if unit == PER_KILOMETER:
        return street_length_m(site, piece_gap_m) / METERS_IN_KILOMETER
    if unit == PER_HECTARE:
        return site.plantable_surface.area / SQUARE_METERS_IN_HECTARE
    raise ConfigurationError(f"unsupported density unit '{unit}'")


def street_length_m(site: SiteModel, piece_gap_m: float) -> float:
    inside = sum(axis.intersection(site.boundary).length for axis in site.street_axes)
    if inside > 0:
        return inside
    return sum(longest_side_m(cluster) for cluster in boundary_clusters(site.boundary, piece_gap_m))


def boundary_clusters(boundary: BaseGeometry, gap_m: float) -> list[BaseGeometry]:
    parts = polygonal_parts(boundary)
    reaches = polygonal_parts(unary_union([part.buffer(gap_m / 2) for part in parts]))
    return [unary_union([part for part in parts if part.intersects(reach)]) for reach in reaches]


def longest_side_m(area: BaseGeometry) -> float:
    corners = list(area.minimum_rotated_rectangle.exterior.coords)
    return max(Point(start).distance(Point(end)) for start, end in zip(corners, corners[1:], strict=False))
