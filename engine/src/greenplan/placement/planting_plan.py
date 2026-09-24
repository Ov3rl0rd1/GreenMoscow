from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from greenplan.constraints.candidate_evaluator import CandidateEvaluatorFactory
from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.requirement_resolver import RequirementResolver
from greenplan.constraints.zone_builder import ZoneBuilder
from greenplan.domain.decisions import PlantingDecision
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.placement.peak_selector import PeakSelector
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.plant_placement_planner import PlantPlacementPlanner
from greenplan.placement.planting_limits import PlantingLimits, PlantingLimitsResolver
from greenplan.placement.planting_profile import PlantingProfile
from greenplan.placement.planting_zones import PlantingZoneBuilder, PlantingZones
from greenplan.placement.raster import SiteRaster
from greenplan.placement.rejection_sampler import RejectionSampler
from greenplan.placement.score_maps import RuleScoreMap, ScoreMapProvider
from greenplan.placement.site_rasterizer import SiteRasterizer

TREE_IDENTIFIER_PREFIX = "T"
SHRUB_IDENTIFIER_PREFIX = "S"
REJECTION_IDENTIFIER_PREFIX = "R"


@dataclass(frozen=True, slots=True, eq=False)
class PlantingPlan:
    trees: tuple[PlantingDecision, ...]
    shrubs: tuple[PlantingDecision, ...]
    rejections: tuple[PlantingDecision, ...]
    limits: PlantingLimits
    tree_raster: SiteRaster
    tree_score: np.ndarray
    tree_zones: PlantingZones


class PlantingPlanComposer:
    def __init__(
        self,
        planner: PlantPlacementPlanner,
        limits_resolver: PlantingLimitsResolver,
        rejection_sampler: RejectionSampler,
        evaluator_factory: CandidateEvaluatorFactory,
        settings: PlacementSettings,
        tree_score_map: ScoreMapProvider,
        shrub_score_map: ScoreMapProvider,
    ) -> None:
        self._planner = planner
        self._limits_resolver = limits_resolver
        self._rejection_sampler = rejection_sampler
        self._evaluator_factory = evaluator_factory
        self._settings = settings
        self._tree_score_map = tree_score_map
        self._shrub_score_map = shrub_score_map

    @classmethod
    def from_knowledge(
        cls,
        knowledge_root: Path,
        settings: PlacementSettings | None = None,
        design: DesignConstraints | None = None,
        tree_score_map: ScoreMapProvider | None = None,
    ) -> "PlantingPlanComposer":
        placement = settings or PlacementSettings()
        constraints = design or DesignConstraints()
        repository = NormsRepository.from_knowledge(knowledge_root)
        resolver = RequirementResolver(
            repository, constraints.unknown_overhead_voltage_kv, constraints.active_activations()
        )
        meter = ClearanceMeter(repository.defaults)
        selector = PeakSelector()
        zone_builder = PlantingZoneBuilder(ZoneBuilder(resolver, meter), resolver, constraints)
        return cls(
            planner=PlantPlacementPlanner(
                zone_builder, SiteRasterizer(placement.cell_size_m, placement.max_raster_cells), selector
            ),
            limits_resolver=PlantingLimitsResolver(repository, placement),
            rejection_sampler=RejectionSampler(
                selector,
                placement.rejection_spacing_m,
                placement.max_rejections_per_reason,
                placement.max_rejections,
                placement.rejection_seed,
            ),
            evaluator_factory=CandidateEvaluatorFactory(resolver, meter, constraints),
            settings=placement,
            tree_score_map=tree_score_map or RuleScoreMap(placement.tree_score),
            shrub_score_map=RuleScoreMap(placement.shrub_score),
        )

    def compose(self, site: SiteModel) -> PlantingPlan:
        limits = self._limits_resolver.resolve(site)
        evaluator = self._evaluator_factory.for_site(site)
        tree_profile = self._tree_profile(limits)
        trees = self._planner.plan(site, tree_profile, evaluator, ())
        tree_positions = [decision.candidate.position for decision in trees.decisions]
        shrubs = self._planner.plan(site, self._shrub_profile(limits), evaluator, tree_positions)
        rejections = self._rejection_sampler.sample(trees.raster, evaluator, tree_profile)
        return PlantingPlan(
            trees=numbered(trees.decisions, TREE_IDENTIFIER_PREFIX),
            shrubs=numbered(shrubs.decisions, SHRUB_IDENTIFIER_PREFIX),
            rejections=numbered(rejections, REJECTION_IDENTIFIER_PREFIX),
            limits=limits,
            tree_raster=trees.raster,
            tree_score=trees.score,
            tree_zones=trees.zones,
        )

    def _tree_profile(self, limits: PlantingLimits) -> PlantingProfile:
        settings = self._settings
        return PlantingProfile(
            target=TREE,
            crown_diameter_m=settings.tree_crown_diameter_m,
            spacing_m=limits.tree_spacing_m,
            max_count=limits.max_trees,
            reference_edge_kind=settings.tree_reference_edge_kind,
            score_map=self._tree_score_map,
            allow_conditional=settings.allow_conditional,
            planned_plant_clearance_m=0.0,
        )

    def _shrub_profile(self, limits: PlantingLimits) -> PlantingProfile:
        settings = self._settings
        return PlantingProfile(
            target=SHRUB,
            crown_diameter_m=settings.shrub_crown_diameter_m,
            spacing_m=limits.shrub_spacing_m,
            max_count=limits.max_shrubs,
            reference_edge_kind=settings.shrub_reference_edge_kind,
            score_map=self._shrub_score_map,
            allow_conditional=settings.allow_conditional,
            planned_plant_clearance_m=settings.min_shrub_distance_to_planned_tree_m,
        )


def numbered(decisions: Sequence[PlantingDecision], prefix: str) -> tuple[PlantingDecision, ...]:
    return tuple(
        replace(decision, candidate=replace(decision.candidate, candidate_id=f"{prefix}-{index:04d}"))
        for index, decision in enumerate(decisions, start=1)
    )
