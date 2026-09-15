from collections.abc import Sequence

from shapely.geometry import Point
from shapely.prepared import prep
from shapely.strtree import STRtree

from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.obstacle_index import ObstacleIndex
from greenplan.constraints.requirement_resolver import RequirementResolver
from greenplan.domain.decisions import (
    OUTSIDE_PLANTABLE_SURFACE,
    OUTSIDE_SITE_BOUNDARY,
    TOO_CLOSE_TO_EXISTING_TREE,
    Clearance,
    PlantCandidate,
    PlantingDecision,
    SiteViolation,
    decision_status,
)
from greenplan.domain.norms import Requirement
from greenplan.domain.site import Obstacle, SiteModel


class CandidateEvaluator:
    def __init__(
        self,
        resolver: RequirementResolver,
        meter: ClearanceMeter,
        site: SiteModel,
        design: DesignConstraints,
    ) -> None:
        self._resolver = resolver
        self._meter = meter
        self._design = design
        self._obstacle_index = ObstacleIndex(site.obstacles)
        self._plantable = prep(site.plantable_surface)
        self._boundary = prep(site.boundary)
        self._kept_tree_positions = [tree.position for tree in site.kept_trees()]
        self._kept_tree_index = STRtree(self._kept_tree_positions) if self._kept_tree_positions else None

    def evaluate(self, candidate: PlantCandidate) -> PlantingDecision:
        clearances = self._clearances(candidate)
        site_violations = self._site_violations(candidate)
        status = decision_status(clearances, site_violations)
        return PlantingDecision(candidate, status, self._reported(clearances), site_violations)

    def _clearances(self, candidate: PlantCandidate) -> list[Clearance]:
        search_radius = (
            self._resolver.max_requirement_distance_m(candidate.crown_diameter_m)
            + self._design.obstacle_search_margin_m
        )
        clearances: list[Clearance] = []
        for obstacle in self._obstacle_index.within(candidate.position, search_radius):
            requirements = self._resolver.resolve(
                obstacle.kind, candidate.target, candidate.crown_diameter_m, candidate.species_name_ru
            )
            clearances.extend(
                self._clearance(candidate.position, obstacle, requirement) for requirement in requirements
            )
        return clearances

    def _clearance(self, position: Point, obstacle: Obstacle, requirement: Requirement) -> Clearance:
        measured = self._meter.measure(position, obstacle, requirement)
        satisfied = measured.actual_m + self._design.clearance_tolerance_m >= requirement.distance_m
        return Clearance(obstacle, requirement, measured.actual_m, satisfied, measured.assumed_outer_radius)

    def _site_violations(self, candidate: PlantCandidate) -> tuple[SiteViolation, ...]:
        violations: list[SiteViolation] = []
        if not self._boundary.contains(candidate.position):
            violations.append(SiteViolation(OUTSIDE_SITE_BOUNDARY))
        if self._design.require_plantable_surface and not self._plantable.contains(candidate.position):
            violations.append(SiteViolation(OUTSIDE_PLANTABLE_SURFACE))
        violations.extend(self._existing_tree_violations(candidate))
        return tuple(violations)

    def _existing_tree_violations(self, candidate: PlantCandidate) -> list[SiteViolation]:
        if self._kept_tree_index is None:
            return []
        required = self._design.existing_tree_clearance_m(candidate.target)
        nearest = self._kept_tree_positions[int(self._kept_tree_index.nearest(candidate.position))]
        actual = candidate.position.distance(nearest)
        return [SiteViolation(TOO_CLOSE_TO_EXISTING_TREE, actual, required)] if actual < required else []

    def _reported(self, clearances: Sequence[Clearance]) -> tuple[Clearance, ...]:
        violated = [clearance for clearance in clearances if not clearance.satisfied]
        tightest_satisfied: dict[tuple[str, str], Clearance] = {}
        for clearance in clearances:
            key = (clearance.requirement.rule_id, clearance.obstacle.kind)
            if clearance.satisfied and (
                key not in tightest_satisfied or clearance.margin_m < tightest_satisfied[key].margin_m
            ):
                tightest_satisfied[key] = clearance
        return tuple(violated) + tuple(tightest_satisfied.values())


class CandidateEvaluatorFactory:
    def __init__(
        self, resolver: RequirementResolver, meter: ClearanceMeter, design: DesignConstraints
    ) -> None:
        self._resolver = resolver
        self._meter = meter
        self._design = design

    def for_site(self, site: SiteModel) -> CandidateEvaluator:
        return CandidateEvaluator(self._resolver, self._meter, site, self._design)
