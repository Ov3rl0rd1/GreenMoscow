from collections.abc import Sequence
from dataclasses import dataclass
from math import floor

import numpy as np
from shapely.geometry import Point
from shapely.strtree import STRtree

from greenplan.constraints.candidate_evaluator import CandidateEvaluator
from greenplan.domain.composition import CompositionElement
from greenplan.domain.decisions import ACCEPTED, CONDITIONALLY_ACCEPTED, PlantCandidate, PlantingDecision
from greenplan.domain.norms import TREE
from greenplan.domain.site import SiteModel
from greenplan.geometry.shapes import outline_lines
from greenplan.placement.composition_planner import (
    ComposedPlanting,
    CompositionField,
    CompositionPlanner,
    Trial,
)
from greenplan.placement.composition_shapes import CompanionLine, Companions, EdgeClassifier, lawn_edges
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
    elements: tuple[CompositionElement, ...] = ()
    field: CompositionField | None = None
    budget: int | None = None


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
        decision = self.trial(point)
        if decision is None:
            return False
        self.decisions.append(decision)
        return True

    def trial(self, point: Point) -> PlantingDecision | None:
        if not self._guard.is_clear(point):
            return None
        candidate = PlantCandidate("", point, self._profile.target, self._profile.crown_diameter_m)
        decision = self._evaluator.evaluate(candidate)
        return decision if decision.status in self._admitted_statuses else None


class PlantPlacementPlanner:
    def __init__(
        self,
        zone_builder: PlantingZoneBuilder,
        rasterizer: SiteRasterizer,
        selector: PeakSelector,
        composer: CompositionPlanner | None = None,
        edge_kinds: Sequence[str] = (),
        edge_simplify_m: float = 0.5,
        edge_reach_m: float = 8.0,
        reserve_share: float = 0.0,
        candidate_area_factor: float = 1.0,
        companion_reach_m: float = 5.5,
    ) -> None:
        self._zone_builder = zone_builder
        self._rasterizer = rasterizer
        self._selector = selector
        self._composer = composer
        self._edge_kinds = tuple(edge_kinds)
        self._edge_simplify_m = edge_simplify_m
        self._edge_reach_m = edge_reach_m
        self._reserve_share = reserve_share
        self._candidate_area_factor = candidate_area_factor
        self._companion_reach_m = companion_reach_m

    def plan(
        self,
        site: SiteModel,
        profile: PlantingProfile,
        evaluator: CandidateEvaluator,
        planned_positions: Sequence[Point],
        companions: Sequence[CompanionLine] = (),
    ) -> PlacementOutcome:
        zones = self._zone_builder.build(site, profile, planned_positions)
        raster = self._rasterizer.rasterize(site, zones, profile.reference_edge_kind)
        guidance = profile.score_map.guide(raster, site)
        admission = _Admission(
            evaluator, profile, PlannedPlantGuard(planned_positions, profile.planned_plant_clearance_m)
        )
        count = guided_count(
            profile.max_count, guidance.expected_count, profile.respects_density_cap, profile.min_count_share
        )
        eligible = eligible_cells(raster, guidance, profile.allow_conditional)
        if count is not None and guidance.candidates is not None:
            cells = count * (profile.spacing_m / raster.grid.cell_size_m) ** 2 * self._candidate_area_factor
            pool = allowed_cells(raster, profile.allow_conditional)
            eligible = widened(eligible, pool, guidance.score, cells)
        if self._composer is not None and profile.composed and count is not None:
            field = CompositionField(
                raster.grid,
                guidance.score,
                eligible & ~raster.conditional,
                raster.clearance_m,
                tuple(lawn_edges(site.plantable_surface, self._edge_simplify_m)),
                eligible,
                self._edge_classifier(site).kind_near,
                raster.allowed & ~raster.conditional,
            )
            budget = floor(count * (1.0 - self._reserve_share))
            composed = self._compose(field, admission, profile, budget, companions)
            return PlacementOutcome(
                composed.decisions,
                raster,
                guidance.score,
                zones,
                guidance.source,
                guidance.expected_count,
                composed.elements,
                field,
                count,
            )
        self._select(raster, guidance, eligible, profile, count, admission)
        return PlacementOutcome(
            tuple(admission.decisions),
            raster,
            guidance.score,
            zones,
            guidance.source,
            guidance.expected_count,
            budget=count,
        )

    def trial(self, evaluator: CandidateEvaluator, profile: PlantingProfile) -> Trial:
        return _Admission(evaluator, profile, PlannedPlantGuard((), 0.0)).trial

    def _compose(
        self,
        field: CompositionField,
        admission: "_Admission",
        profile: PlantingProfile,
        count: int,
        companions: Sequence[CompanionLine] = (),
    ) -> ComposedPlanting:
        composer = self._composer
        if profile.target == TREE:
            return composer.compose_trees(field, admission.trial, profile.target, profile.spacing_m, count)
        return composer.compose_shrubs(
            field,
            admission.trial,
            profile.target,
            profile.spacing_m,
            count,
            Companions(companions, self._companion_reach_m),
        )

    def _select(
        self,
        raster: SiteRaster,
        guidance: PlacementGuidance,
        eligible: np.ndarray,
        profile: PlantingProfile,
        count: int | None,
        admission: "_Admission",
    ) -> None:
        if guidance.candidates is not None and count is not None:
            self._selector.select_by_groups(
                raster.grid, guidance.score, eligible, profile.spacing_m, count, admission
            )
        else:
            self._selector.select(raster.grid, guidance.score, eligible, profile.spacing_m, count, admission)

    def _edge_classifier(self, site: SiteModel) -> EdgeClassifier:
        lines = {
            kind: [line for obstacle in site.obstacles_of(kind) for line in outline_lines(obstacle.geometry)]
            for kind in self._edge_kinds
        }
        return EdgeClassifier(lines, self._edge_reach_m)


def allowed_cells(raster: SiteRaster, allow_conditional: bool) -> np.ndarray:
    return raster.allowed if allow_conditional else raster.allowed & ~raster.conditional


def eligible_cells(raster: SiteRaster, guidance: PlacementGuidance, allow_conditional: bool) -> np.ndarray:
    eligible = allowed_cells(raster, allow_conditional)
    return eligible if guidance.candidates is None else eligible & guidance.candidates


def widened(eligible: np.ndarray, pool: np.ndarray, score: np.ndarray, needed_cells: float) -> np.ndarray:
    extra = pool & ~eligible
    missing = min(int(needed_cells) - int(eligible.sum()), int(extra.sum()))
    if missing <= 0:
        return eligible
    ranked = np.where(extra, score, -np.inf).ravel()
    chosen = np.argpartition(-ranked, missing - 1)[:missing]
    result = eligible.copy()
    result.flat[chosen] = True
    return result


def guided_count(
    normative_max: int | None, expected: int | None, respect_cap: bool = True, min_share: float = 0.0
) -> int | None:
    if expected is None:
        return normative_max
    if normative_max is None:
        return expected
    expected = max(expected, floor(normative_max * min_share))
    return expected if not respect_cap else min(normative_max, expected)
