from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Point
from shapely.strtree import STRtree

from greenplan.constraints.candidate_evaluator import CandidateEvaluator
from greenplan.domain.decisions import ACCEPTED, CONDITIONALLY_ACCEPTED, PlantCandidate, PlantingDecision
from greenplan.domain.site import SiteModel
from greenplan.placement.peak_selector import PeakSelector
from greenplan.placement.planting_profile import PlantingProfile
from greenplan.placement.planting_zones import PlantingZoneBuilder, PlantingZones
from greenplan.placement.raster import SiteRaster
from greenplan.placement.score_maps import RULES_GUIDANCE, PlacementGuidance
from greenplan.placement.site_rasterizer import SiteRasterizer


@dataclass(frozen=True, slots=True, eq=False)
class PlacementOutcome:
    decisions: tuple[PlantingDecision, ...]
    raster: SiteRaster
    score: np.ndarray
    zones: PlantingZones
    guidance_source: str = RULES_GUIDANCE
    expected_count: int | None = None


class PlannedPlantGuard:
    def __init__(self, positions: Sequence[Point], clearance_m: float) -> None:
        self._positions = list(positions)
        self._clearance_m = clearance_m
        self._tree = STRtree(self._positions) if self._positions and clearance_m > 0 else None

    def is_clear(self, point: Point) -> bool:
        if self._tree is None:
            return True
        nearest = self._positions[int(self._tree.nearest(point))]
        return point.distance(nearest) >= self._clearance_m


class _Admission:
    def __init__(
        self, evaluator: CandidateEvaluator, profile: PlantingProfile, guard: PlannedPlantGuard
    ) -> None:
        self._evaluator = evaluator
        self._profile = profile
        self._guard = guard
        self._admitted_statuses = (
            {ACCEPTED, CONDITIONALLY_ACCEPTED} if profile.allow_conditional else {ACCEPTED}
        )
        self.decisions: list[PlantingDecision] = []

    def __call__(self, point: Point) -> bool:
        if not self._guard.is_clear(point):
            return False
        candidate = PlantCandidate("", point, self._profile.target, self._profile.crown_diameter_m)
        decision = self._evaluator.evaluate(candidate)
        if decision.status not in self._admitted_statuses:
            return False
        self.decisions.append(decision)
        return True


class PlantPlacementPlanner:
    def __init__(
        self, zone_builder: PlantingZoneBuilder, rasterizer: SiteRasterizer, selector: PeakSelector
    ) -> None:
        self._zone_builder = zone_builder
        self._rasterizer = rasterizer
        self._selector = selector

    def plan(
        self,
        site: SiteModel,
        profile: PlantingProfile,
        evaluator: CandidateEvaluator,
        planned_positions: Sequence[Point],
    ) -> PlacementOutcome:
        zones = self._zone_builder.build(site, profile, planned_positions)
        raster = self._rasterizer.rasterize(site, zones, profile.reference_edge_kind)
        guidance = profile.score_map.guide(raster, site)
        admission = _Admission(
            evaluator, profile, PlannedPlantGuard(planned_positions, profile.planned_plant_clearance_m)
        )
        eligible = eligible_cells(raster, guidance, profile.allow_conditional)
        count = guided_count(profile.max_count, guidance.expected_count)
        if guidance.candidates is not None and count is not None:
            self._selector.select_by_groups(
                raster.grid, guidance.score, eligible, profile.spacing_m, count, admission
            )
        else:
            self._selector.select(raster.grid, guidance.score, eligible, profile.spacing_m, count, admission)
        return PlacementOutcome(
            tuple(admission.decisions),
            raster,
            guidance.score,
            zones,
            guidance.source,
            guidance.expected_count,
        )


def eligible_cells(raster: SiteRaster, guidance: PlacementGuidance, allow_conditional: bool) -> np.ndarray:
    eligible = raster.allowed if allow_conditional else raster.allowed & ~raster.conditional
    return eligible if guidance.candidates is None else eligible & guidance.candidates


def guided_count(normative_max: int | None, expected: int | None) -> int | None:
    if expected is None:
        return normative_max
    if normative_max is None:
        return expected
    return min(normative_max, expected)
