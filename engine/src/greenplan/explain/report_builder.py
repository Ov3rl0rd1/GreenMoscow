from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from greenplan.domain.decisions import CONDITIONALLY_ACCEPTED
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.explain.explanation_builder import DEFAULT_MAX_SATISFIED_CLEARANCES, ExplanationBuilder
from greenplan.explain.explanation_model import ClearanceView, PlantExplanation
from greenplan.explain.number_format import format_number, structure_value
from greenplan.explain.report_model import (
    AppliedNormRow,
    PlantingReport,
    RejectionReasonRow,
    ReportSummary,
    SpeciesCount,
)
from greenplan.knowledge.explanation_terms import ExplanationTerms
from greenplan.placement.planting_plan import PlantingPlan
from greenplan.species.species_selector import SpeciesOutcome

PACKAGE_NAME = "greenplan"
UNKNOWN_VERSION = "unknown"


@dataclass
class _NormAccumulator:
    first: ClearanceView
    mentions: int = 0
    binding: int = 0
    counted_plants: set[str] = field(default_factory=set)


class ReportBuilder:
    def __init__(self, explanations: ExplanationBuilder, engine_version: str) -> None:
        self._explanations = explanations
        self._engine_version = engine_version

    @classmethod
    def from_knowledge(
        cls, knowledge_root: Path, max_satisfied_clearances: int = DEFAULT_MAX_SATISFIED_CLEARANCES
    ) -> "ReportBuilder":
        return cls(
            ExplanationBuilder.from_knowledge(knowledge_root, max_satisfied_clearances), installed_version()
        )

    def build(
        self, title: str, site: SiteModel, plan: PlantingPlan, species: SpeciesOutcome
    ) -> PlantingReport:
        plants = tuple(self._explanations.for_assignment(assignment) for assignment in species.assignments)
        rejected_decisions = (*plan.rejections, *species.rejections)
        rejections = tuple(self._explanations.for_decision(decision) for decision in rejected_decisions)
        terms = self._explanations.terms
        return PlantingReport(
            title=title,
            engine_version=self._engine_version,
            summary=_summary(site, plan, species, plants, rejections, terms),
            applied_norms=applied_norm_rows((*plants, *rejections), terms),
            rejection_reasons=rejection_reason_rows(rejections, terms),
            plants=plants,
            rejections=rejections,
        )


def applied_norm_rows(
    explanations: Sequence[PlantExplanation], terms: ExplanationTerms
) -> tuple[AppliedNormRow, ...]:
    accumulators: dict[str, _NormAccumulator] = {}
    for explanation in explanations:
        for clearance in explanation.clearances:
            accumulator = accumulators.setdefault(clearance.rule_id, _NormAccumulator(clearance))
            if explanation.plant_id in accumulator.counted_plants:
                continue
            accumulator.counted_plants.add(explanation.plant_id)
            accumulator.mentions += 1
            accumulator.binding += 0 if clearance.satisfied else 1
    rows = [
        AppliedNormRow(
            rule_id=rule_id,
            description_ru=norm_description(accumulator.first, terms),
            severity_ru=terms.severity(accumulator.first.severity),
            citations=accumulator.first.citations,
            mentions=accumulator.mentions,
            binding=accumulator.binding,
        )
        for rule_id, accumulator in accumulators.items()
    ]
    return tuple(sorted(rows, key=lambda row: (-row.binding, -row.mentions, row.rule_id)))


def rejection_reason_rows(
    rejections: Sequence[PlantExplanation], terms: ExplanationTerms
) -> tuple[RejectionReasonRow, ...]:
    counts = Counter(explanation.primary_reason_code for explanation in rejections)
    descriptions = {code: _reason_description(code, rejections, terms) for code in counts}
    return tuple(RejectionReasonRow(code, descriptions[code], count) for code, count in counts.most_common())


def norm_description(clearance: ClearanceView, terms: ExplanationTerms) -> str:
    obstacle = terms.obstacle(clearance.obstacle_kind)
    distance = format_number(clearance.base_required_m)
    return f"{terms.norm_kind(clearance.rule_type)} {obstacle.from_ru}: {distance} м"


def installed_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return UNKNOWN_VERSION


def _reason_description(code: str, rejections: Sequence[PlantExplanation], terms: ExplanationTerms) -> str:
    for explanation in rejections:
        for clearance in explanation.clearances:
            if clearance.rule_id == code:
                return norm_description(clearance, terms)
    return terms.site_violation(code).text_ru


def _summary(
    site: SiteModel,
    plan: PlantingPlan,
    species: SpeciesOutcome,
    plants: Sequence[PlantExplanation],
    rejections: Sequence[PlantExplanation],
    terms: ExplanationTerms,
) -> ReportSummary:
    cell_area = plan.tree_raster.grid.cell_size_m**2
    diagnostics = site.diagnostics
    return ReportSummary(
        trees=sum(1 for plant in plants if plant.plant_type == TREE),
        shrubs=sum(1 for plant in plants if plant.plant_type == SHRUB),
        conditional=sum(1 for plant in plants if plant.status == CONDITIONALLY_ACCEPTED),
        rejected=len(rejections),
        species=_species_counts(species),
        plantable_area_m2=structure_value(site.plantable_surface.area),
        tree_allowed_area_m2=structure_value(float(plan.tree_raster.allowed.sum()) * cell_area),
        max_trees=plan.limits.max_trees,
        max_shrubs=plan.limits.max_shrubs,
        tree_spacing_m=plan.limits.tree_spacing_m,
        shrub_spacing_m=plan.limits.shrub_spacing_m,
        boundary_source=diagnostics.boundary_source,
        lawn_source=diagnostics.lawn_source,
        annotated_network_share=structure_value(diagnostics.annotated_network_share),
        unresolved_references=diagnostics.unresolved_references,
        root_barrier_length_m=structure_value(sum(plant.root_barrier_length_m for plant in plants)),
        warnings=tuple(terms.site_warning(code) for code in diagnostics.warnings),
        territory_ru=species.territory_note.reason_ru if species.territory_note else "",
        excluded_species=tuple(f"{item.name_ru} — {item.reason_ru}" for item in species.excluded),
    )


def _species_counts(species: SpeciesOutcome) -> tuple[SpeciesCount, ...]:
    counts = Counter(
        (assignment.species.name_ru, assignment.decision.candidate.target)
        for assignment in species.assignments
    )
    return tuple(SpeciesCount(name, target, count) for (name, target), count in counts.most_common())
