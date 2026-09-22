from dataclasses import dataclass

from greenplan.explain.explanation_model import CitationView, PlantExplanation
from greenplan.explain.plan_metrics import CostEstimate, PlanMetrics, VolumeStatement


@dataclass(frozen=True, slots=True)
class SpeciesCount:
    name_ru: str
    plant_type: str
    count: int


@dataclass(frozen=True, slots=True)
class AppliedNormRow:
    rule_id: str
    description_ru: str
    severity_ru: str
    citations: tuple[CitationView, ...]
    mentions: int
    binding: int


@dataclass(frozen=True, slots=True)
class RejectionReasonRow:
    code: str
    description_ru: str
    count: int


@dataclass(frozen=True, slots=True)
class ReportSummary:
    trees: int
    shrubs: int
    conditional: int
    rejected: int
    species: tuple[SpeciesCount, ...]
    plantable_area_m2: float
    tree_allowed_area_m2: float
    max_trees: int
    max_shrubs: int
    tree_spacing_m: float
    shrub_spacing_m: float
    boundary_source: str
    lawn_source: str
    annotated_network_share: float
    unresolved_references: tuple[str, ...]
    root_barrier_length_m: float = 0.0
    warnings: tuple[str, ...] = ()
    territory_ru: str = ""
    excluded_species: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlantingReport:
    title: str
    engine_version: str
    summary: ReportSummary
    applied_norms: tuple[AppliedNormRow, ...]
    rejection_reasons: tuple[RejectionReasonRow, ...]
    plants: tuple[PlantExplanation, ...]
    rejections: tuple[PlantExplanation, ...]
    metrics: PlanMetrics | None = None
    volumes: VolumeStatement | None = None
    cost: CostEstimate | None = None
