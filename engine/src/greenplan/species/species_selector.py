from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import floor
from pathlib import Path

from shapely.geometry import Point

from greenplan.constraints.candidate_evaluator import CandidateEvaluator, CandidateEvaluatorFactory
from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.requirement_resolver import RequirementResolver
from greenplan.domain.decisions import (
    ACCEPTED,
    CONDITIONALLY_ACCEPTED,
    NO_SUITABLE_SPECIES,
    REJECTED,
    PlantCandidate,
    PlantingDecision,
    SiteViolation,
)
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.knowledge.invasive_registry import InvasiveRegistry, InvasiveVerdict
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.knowledge.official_assortment import OfficialAssortment
from greenplan.knowledge.plant_catalog import PlantCatalog, Species
from greenplan.knowledge.territory_catalog import TerritoryCatalog
from greenplan.species.selection_texts import SelectionReason, SelectionTexts
from greenplan.species.site_context import PlantingContext, SiteContextDetector
from greenplan.species.species_settings import SpeciesSettings
from greenplan.species.species_suitability import RankedSpecies, SpeciesSuitability
from greenplan.species.territory_policy import TerritoryPolicy

STATUS_RANK = {ACCEPTED: 0, CONDITIONALLY_ACCEPTED: 1}
BEST_ASSIGNMENT_RANK = (0, 0)
LOWER_RANK = "lower_rank"
REJECTED_OUTCOME = "rejected"
CONDITIONAL_OUTCOME = "conditional"
ADVISORY_OUTCOME = "advisory"


@dataclass(frozen=True, slots=True)
class SpeciesAlternative:
    name_ru: str
    reason_ru: str


@dataclass(frozen=True, slots=True)
class SpeciesAssignment:
    decision: PlantingDecision
    species: Species
    context: PlantingContext
    invasive: InvasiveVerdict
    reasons: tuple[SelectionReason, ...]
    alternatives: tuple[SpeciesAlternative, ...] = ()


@dataclass(frozen=True, slots=True)
class SpeciesOutcome:
    assignments: tuple[SpeciesAssignment, ...]
    rejections: tuple[PlantingDecision, ...]
    excluded: tuple[SpeciesAlternative, ...] = ()
    territory_note: SelectionReason | None = None
    territory_id: str = ""


class _AssignmentMemory:
    def __init__(self, radius_m: float) -> None:
        self._radius_m = radius_m
        self._buckets: dict[tuple[int, int], list[tuple[Point, str]]] = defaultdict(list)

    def remember(self, position: Point, species_key: str) -> None:
        if self._radius_m > 0:
            self._buckets[self._key(position)].append((position, species_key))

    def species_near(self, position: Point) -> list[str]:
        if self._radius_m <= 0:
            return []
        key_x, key_y = self._key(position)
        nearby = sorted(
            (position.distance(other), species_key)
            for bucket_x in (key_x - 1, key_x, key_x + 1)
            for bucket_y in (key_y - 1, key_y, key_y + 1)
            for other, species_key in self._buckets.get((bucket_x, bucket_y), ())
            if position.distance(other) <= self._radius_m
        )
        return list(dict.fromkeys(species_key for _distance, species_key in nearby))

    def _key(self, position: Point) -> tuple[int, int]:
        return floor(position.x / self._radius_m), floor(position.y / self._radius_m)


class SpeciesSelector:
    def __init__(
        self,
        suitability: SpeciesSuitability,
        evaluator: CandidateEvaluator,
        detector: SiteContextDetector,
        settings: SpeciesSettings,
        texts: SelectionTexts | None = None,
    ) -> None:
        self._suitability = suitability
        self._evaluator = evaluator
        self._detector = detector
        self._settings = settings
        self._texts = texts

    def assign(self, decisions: Sequence[PlantingDecision]) -> SpeciesOutcome:
        memories: dict[str, _AssignmentMemory] = {}
        element_species: dict[str, str] = {}
        usage = _SpeciesUsage()
        assignments: list[SpeciesAssignment] = []
        rejections: list[PlantingDecision] = []
        for decision in decisions:
            target = decision.candidate.target
            memory = memories.setdefault(
                target, _AssignmentMemory(self._settings.grouping_distance_m(target))
            )
            assignment = self._assignment(decision, memory, usage, element_species)
            if assignment is None:
                rejections.append(without_species(decision))
                continue
            element_species.setdefault(decision.candidate.element_id, assignment.species.key)
            memory.remember(decision.candidate.position, assignment.species.key)
            usage.record(target, assignment.species.key)
            assignments.append(assignment)
        return SpeciesOutcome(
            tuple(assignments),
            tuple(rejections),
            self._excluded(),
            self._territory_note(),
            self._territory_id(),
        )

    def _territory_id(self) -> str:
        policy = self._suitability.territory
        return policy.category.category_id if policy is not None else ""

    def _excluded(self) -> tuple[SpeciesAlternative, ...]:
        found = [*self._suitability.excluded(TREE), *self._suitability.excluded(SHRUB)]
        return tuple(SpeciesAlternative(species.name_ru, text) for species, text in found)

    def _territory_note(self) -> SelectionReason | None:
        policy = self._suitability.territory
        return policy.composition_reason() if policy is not None else None

    def _assignment(
        self,
        decision: PlantingDecision,
        memory: _AssignmentMemory,
        usage: "_SpeciesUsage",
        element_species: dict[str, str],
    ) -> SpeciesAssignment | None:
        position = decision.candidate.position
        target = decision.candidate.target
        context = self._detector.detect(position)
        ranked = self._diversified(self._suitability.ranked(target, context), target, usage)
        ordered = neighbour_species_first(ranked, preferred_species(decision, memory, element_species))
        outcomes: dict[str, str] = {}
        best: SpeciesAssignment | None = None
        for item in ordered:
            evaluated = self._evaluator.evaluate(with_species(decision.candidate, item.species))
            if evaluated.status == REJECTED:
                outcomes[item.species.key] = REJECTED_OUTCOME
                continue
            assignment = SpeciesAssignment(evaluated, item.species, context, item.invasive, item.reasons)
            outcomes[item.species.key] = outcome_of(assignment)
            if best is None or assignment_rank(assignment) < assignment_rank(best):
                best = assignment
            if assignment_rank(assignment) == BEST_ASSIGNMENT_RANK:
                break
        if best is None:
            return None
        return replace(best, alternatives=self._alternatives(ordered, best, outcomes))

    def _alternatives(
        self, ordered: Sequence[RankedSpecies], chosen: SpeciesAssignment, outcomes: dict[str, str]
    ) -> tuple[SpeciesAlternative, ...]:
        if self._texts is None:
            return ()
        others = [item for item in ordered if item.species.key != chosen.species.key]
        return tuple(
            SpeciesAlternative(
                item.species.name_ru, self._texts.alternative(outcomes.get(item.species.key, LOWER_RANK))
            )
            for item in others[: self._settings.max_alternatives]
        )

    def _diversified(
        self, ranked: Sequence[RankedSpecies], target: str, usage: "_SpeciesUsage"
    ) -> list[RankedSpecies]:
        settings = self._settings
        used = usage.distinct(target)
        bonus = settings.palette_bonus if len(used) >= settings.palette_size(target) else 0.0
        return sorted(
            ranked,
            key=lambda item: (
                -(
                    item.score
                    - settings.diversity_penalty * usage.share(target, item.species.key)
                    + (bonus if item.species.key in used else 0.0)
                )
            ),
        )


def outcome_of(assignment: SpeciesAssignment) -> str:
    decision = assignment.decision
    if decision.status == CONDITIONALLY_ACCEPTED:
        return CONDITIONAL_OUTCOME
    return ADVISORY_OUTCOME if decision.advisory_clearances else LOWER_RANK


def assignment_rank(assignment: SpeciesAssignment) -> tuple[int, int]:
    decision = assignment.decision
    return (
        STATUS_RANK.get(decision.status, len(STATUS_RANK)),
        1 if decision.advisory_clearances else 0,
    )


class _SpeciesUsage:
    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str]] = Counter()
        self._totals: Counter[str] = Counter()

    def record(self, target: str, species_key: str) -> None:
        self._counts[(target, species_key)] += 1
        self._totals[target] += 1

    def share(self, target: str, species_key: str) -> float:
        total = self._totals[target]
        return self._counts[(target, species_key)] / total if total else 0.0

    def distinct(self, target: str) -> set[str]:
        return {species_key for used_target, species_key in self._counts if used_target == target}


class SpeciesSelectorFactory:
    def __init__(
        self,
        suitability: SpeciesSuitability,
        evaluator_factory: CandidateEvaluatorFactory,
        settings: SpeciesSettings,
        texts: SelectionTexts | None = None,
    ) -> None:
        self._suitability = suitability
        self._evaluator_factory = evaluator_factory
        self._settings = settings
        self._texts = texts

    @classmethod
    def from_knowledge(
        cls,
        knowledge_root: Path,
        settings: SpeciesSettings | None = None,
        design: DesignConstraints | None = None,
        territory_category: str | None = None,
    ) -> "SpeciesSelectorFactory":
        effective = settings or SpeciesSettings()
        constraints = design or DesignConstraints()
        repository = NormsRepository.from_knowledge(knowledge_root)
        resolver = RequirementResolver(
            repository, constraints.unknown_overhead_voltage_kv, constraints.active_activations()
        )
        evaluator_factory = CandidateEvaluatorFactory(
            resolver, ClearanceMeter(repository.defaults), constraints
        )
        catalog = PlantCatalog.from_file(knowledge_root / "plants" / "assortment.yaml")
        registry = InvasiveRegistry.from_file(knowledge_root / "plants" / "invasive_moscow.yaml")
        texts = SelectionTexts.from_knowledge(knowledge_root)
        territories = TerritoryCatalog.from_knowledge(knowledge_root)
        policy = TerritoryPolicy(
            territories,
            territories.category(territory_category),
            texts,
            OfficialAssortment.from_knowledge(knowledge_root),
        )
        suitability = SpeciesSuitability(catalog, registry, effective, policy, texts)
        return cls(suitability, evaluator_factory, effective, texts)

    def for_site(self, site: SiteModel) -> SpeciesSelector:
        return SpeciesSelector(
            self._suitability,
            self._evaluator_factory.for_site(site),
            SiteContextDetector(site, self._settings),
            self._settings,
            self._texts,
        )


def preferred_species(
    decision: PlantingDecision, memory: _AssignmentMemory, element_species: dict[str, str]
) -> list[str]:
    element_id = decision.candidate.element_id
    if not element_id:
        return memory.species_near(decision.candidate.position)
    return [element_species[element_id]] if element_id in element_species else []


def neighbour_species_first(
    ranked: Sequence[RankedSpecies], neighbour_keys: Sequence[str]
) -> list[RankedSpecies]:
    order = {key: index for index, key in enumerate(neighbour_keys)}
    return sorted(ranked, key=lambda item: order.get(item.species.key, len(order)))


def with_species(candidate: PlantCandidate, species: Species) -> PlantCandidate:
    return replace(
        candidate,
        crown_diameter_m=species.crown_diameter_m,
        species_key=species.key,
        species_name_ru=species.name_ru,
    )


def without_species(decision: PlantingDecision) -> PlantingDecision:
    return replace(
        decision,
        status=REJECTED,
        site_violations=(*decision.site_violations, SiteViolation(NO_SUITABLE_SPECIES)),
    )
