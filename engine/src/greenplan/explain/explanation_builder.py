from dataclasses import replace
from pathlib import Path

from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.constraints.root_barrier_planner import RootBarrier, RootBarrierPlanner, total_length_m
from greenplan.domain.composition import HEDGE, ROW, CompositionElement
from greenplan.domain.decisions import Clearance, PlantingDecision, SiteViolation
from greenplan.domain.norms import ADVISORY, CONDITIONAL, CONDITIONAL_MEASURE, PROHIBITIVE
from greenplan.explain.citation_policy import CitationPolicy
from greenplan.explain.explanation_model import (
    AlternativeView,
    ClearanceView,
    CompetingView,
    ElementView,
    PlantExplanation,
    ReasonView,
    SpeciesView,
    ViolationView,
)
from greenplan.explain.number_format import structure_value
from greenplan.explain.text_renderer import ExplanationTextRenderer
from greenplan.knowledge.explanation_terms import ExplanationTerms
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.species.species_selector import SpeciesAssignment

SEVERITY_ORDER = {PROHIBITIVE: 0, CONDITIONAL: 1, CONDITIONAL_MEASURE: 2, ADVISORY: 3}
DEFAULT_MAX_SATISFIED_CLEARANCES = 3

LAWN_EDGE = "lawn_edge"
LINE_ELEMENT_KINDS = frozenset({ROW, HEDGE})


def _worst_per_rule_and_obstacle_kind(clearances: list[Clearance]) -> list[Clearance]:
    worst: dict[tuple[str, str], Clearance] = {}
    for clearance in clearances:
        key = (clearance.requirement.rule_id, clearance.obstacle.kind)
        if key not in worst or clearance.margin_m < worst[key].margin_m:
            worst[key] = clearance
    return list(worst.values())


def line_edge_of(kind: str) -> str:
    return LAWN_EDGE if kind in LINE_ELEMENT_KINDS else ""


def barrier_planner_of(repository: NormsRepository) -> RootBarrierPlanner | None:
    if repository.root_barrier is None:
        return None
    return RootBarrierPlanner(
        ClearanceMeter(repository.defaults), repository.root_barrier.network_to_barrier_m
    )


def barrier_coordinates(barrier: RootBarrier) -> tuple[tuple[float, float], ...]:
    return tuple((structure_value(x), structure_value(y)) for x, y, *_rest in barrier.line.coords)


class ExplanationBuilder:
    def __init__(
        self,
        citations: CitationPolicy,
        terms: ExplanationTerms,
        renderer: ExplanationTextRenderer,
        crown_rule_source_ref: str,
        max_satisfied_clearances: int,
        barrier_planner: RootBarrierPlanner | None = None,
    ) -> None:
        self._citations = citations
        self._terms = terms
        self._renderer = renderer
        self._crown_rule_source_ref = crown_rule_source_ref
        self._max_satisfied_clearances = max_satisfied_clearances
        self._barrier_planner = barrier_planner

    @classmethod
    def from_knowledge(
        cls, knowledge_root: Path, max_satisfied_clearances: int = DEFAULT_MAX_SATISFIED_CLEARANCES
    ) -> "ExplanationBuilder":
        repository = NormsRepository.from_knowledge(knowledge_root)
        terms = ExplanationTerms.from_file(knowledge_root / "rules" / "explanation_terms.yaml")
        return cls(
            CitationPolicy(repository.citations),
            terms,
            ExplanationTextRenderer(terms),
            repository.defaults.crown_rule_source_ref,
            max_satisfied_clearances,
            barrier_planner_of(repository),
        )

    @property
    def terms(self) -> ExplanationTerms:
        return self._terms

    def for_assignment(
        self, assignment: SpeciesAssignment, element: CompositionElement | None = None
    ) -> PlantExplanation:
        return self._explanation(assignment.decision, self._species_view(assignment), element)

    def for_decision(self, decision: PlantingDecision) -> PlantExplanation:
        return self._explanation(decision, None)

    def _explanation(
        self,
        decision: PlantingDecision,
        species: SpeciesView | None,
        element: CompositionElement | None = None,
    ) -> PlantExplanation:
        candidate = decision.candidate
        barriers = self._barrier_planner.barriers(decision) if self._barrier_planner else ()
        draft = PlantExplanation(
            plant_id=candidate.candidate_id,
            status=decision.status,
            plant_type=candidate.target,
            x=structure_value(candidate.position.x),
            y=structure_value(candidate.position.y),
            crown_diameter_m=structure_value(candidate.crown_diameter_m),
            species=species,
            clearances=self._clearance_views(decision),
            violations=tuple(self._violation_view(violation) for violation in decision.site_violations),
            explanation_ru="",
            root_barriers=tuple(barrier_coordinates(barrier) for barrier in barriers),
            root_barrier_length_m=structure_value(total_length_m(barriers)),
            element=self._element_view(element),
        )
        return replace(draft, explanation_ru=self._renderer.render(draft))

    def _element_view(self, element: CompositionElement | None) -> ElementView | None:
        if element is None:
            return None
        terms = self._terms.element(element.kind)
        companion = self._terms.element_companion() if element.companion_id else None
        return ElementView(
            element_id=element.element_id,
            kind=element.kind,
            name_ru=terms.name_ru,
            size=element.size,
            spacing_m=structure_value(element.spacing_m),
            edge_ru=self._terms.element_edge(element.edge_kind or line_edge_of(element.kind)),
            purpose_ru=f"{terms.purpose_ru}; {companion.purpose_ru}" if companion else terms.purpose_ru,
            rows=element.rows,
            companion_id=element.companion_id,
            companion_ru=companion.name_ru if companion else "",
        )

    def _clearance_views(self, decision: PlantingDecision) -> tuple[ClearanceView, ...]:
        violated = sorted(
            _worst_per_rule_and_obstacle_kind(
                [clearance for clearance in decision.clearances if not clearance.satisfied]
            ),
            key=lambda clearance: SEVERITY_ORDER.get(clearance.requirement.severity, len(SEVERITY_ORDER)),
        )
        satisfied = sorted(
            (clearance for clearance in decision.clearances if clearance.satisfied),
            key=lambda clearance: clearance.margin_m,
        )[: self._max_satisfied_clearances]
        return tuple(self._clearance_view(clearance) for clearance in violated + satisfied)

    def _clearance_view(self, clearance: Clearance) -> ClearanceView:
        requirement = clearance.requirement
        obstacle = clearance.obstacle
        actual = structure_value(clearance.actual_m)
        required = structure_value(requirement.distance_m)
        return ClearanceView(
            rule_id=requirement.rule_id,
            rule_type=requirement.rule_type,
            severity=requirement.severity,
            obstacle_kind=obstacle.kind,
            obstacle_ru=self._terms.obstacle(obstacle.kind).name_ru,
            obstacle_layer=obstacle.layer,
            obstacle_source=obstacle.source_name,
            evidence=obstacle.evidence,
            measurement_ru=self._terms.measurement(requirement.measurement_mode),
            actual_m=actual,
            required_m=required,
            base_required_m=structure_value(requirement.base_distance_m),
            crown_increment_m=structure_value(requirement.crown_increment_m),
            margin_m=structure_value(actual - required),
            satisfied=clearance.satisfied,
            assumed_outer_radius=clearance.assumed_outer_radius,
            condition_ru=requirement.condition_ru,
            is_assumption=requirement.is_assumption,
            citations=self._citations.views(requirement.source_refs),
            crown_rule_citations=self._crown_rule_citations(requirement.crown_increment_m),
            competing=tuple(
                CompetingView(self._citations.view(item.source_ref), item.distance_m)
                for item in requirement.competing
            ),
        )

    def _crown_rule_citations(self, crown_increment_m: float):
        if crown_increment_m <= 0 or not self._crown_rule_source_ref:
            return ()
        return self._citations.views((self._crown_rule_source_ref,))

    def _violation_view(self, violation: SiteViolation) -> ViolationView:
        terms = self._terms.site_violation(violation.code)
        return ViolationView(
            code=violation.code,
            text_ru=terms.text_ru,
            actual_m=None if violation.actual_m is None else structure_value(violation.actual_m),
            required_m=None if violation.required_m is None else structure_value(violation.required_m),
            citations=self._citations.views(terms.source_refs),
        )

    def _species_view(self, assignment: SpeciesAssignment) -> SpeciesView:
        species = assignment.species
        verdict = assignment.invasive
        invasive_terms = self._terms.invasive(verdict.status)
        return SpeciesView(
            key=species.key,
            name_ru=species.name_ru,
            latin=species.latin,
            crown_diameter_m=structure_value(species.crown_diameter_m),
            height_m=structure_value(species.height_m),
            invasive_status=verdict.status,
            invasive_text_ru=invasive_terms.text_ru,
            invasive_citations=self._citations.views((*verdict.source_refs, *invasive_terms.source_refs)),
            reasons=tuple(
                ReasonView(
                    reason.code,
                    reason.reason_ru,
                    self._citations.views((reason.source_ref,)) if reason.source_ref else (),
                )
                for reason in assignment.reasons
                if reason.reason_ru
            ),
            alternatives=tuple(
                AlternativeView(item.name_ru, item.reason_ru) for item in assignment.alternatives
            ),
        )
