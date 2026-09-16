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
from greenplan.domain.site import SiteModel
from greenplan.knowledge.invasive_registry import InvasiveRegistry, InvasiveVerdict
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.knowledge.plant_catalog import PlantCatalog, Species
from greenplan.species.site_context import PlantingContext, SiteContextDetector
from greenplan.species.species_settings import SpeciesSettings
from greenplan.species.species_suitability import RankedSpecies, SelectionReason, SpeciesSuitability

STATUS_RANK = {ACCEPTED: 0, CONDITIONALLY_ACCEPTED: 1}
BEST_ASSIGNMENT_RANK = (0, 0)


@dataclass(frozen=True, slots=True)
class SpeciesAssignment:
    decision: PlantingDecision
    species: Species
    context: PlantingContext
    invasive: InvasiveVerdict
    reasons: tuple[SelectionReason, ...]


@dataclass(frozen=True, slots=True)
class SpeciesOutcome:
    assignments: tuple[SpeciesAssignment, ...]
    rejections: tuple[PlantingDecision, ...]


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
    ) -> None:
        self._suitability = suitability
        self._evaluator = evaluator
        self._detector = detector
        self._settings = settings

    def assign(self, decisions: Sequence[PlantingDecision]) -> SpeciesOutcome:
        memories: dict[str, _AssignmentMemory] = {}
        usage = _SpeciesUsage()
        assignments: list[SpeciesAssignment] = []
        rejections: list[PlantingDecision] = []
        for decision in decisions:
            target = decision.candidate.target
            memory = memories.setdefault(
                target, _AssignmentMemory(self._settings.grouping_distance_m(target))
            )
            assignment = self._assignment(decision, memory, usage)
            if assignment is None:
                rejections.append(without_species(decision))
                continue
            memory.remember(decision.candidate.position, assignment.species.key)
            usage.record(target, assignment.species.key)
            assignments.append(assignment)
        return SpeciesOutcome(tuple(assignments), tuple(rejections))

    def _assignment(
        self, decision: PlantingDecision, memory: _AssignmentMemory, usage: "_SpeciesUsage"
    ) -> SpeciesAssignment | None:
        position = decision.candidate.position
        target = decision.candidate.target
        context = self._detector.detect(position)
        ranked = self._diversified(self._suitability.ranked(target, context), target, usage)
        best: SpeciesAssignment | None = None
        for item in neighbour_species_first(ranked, memory.species_near(position)):
            evaluated = self._evaluator.evaluate(with_species(decision.candidate, item.species))
            if evaluated.status == REJECTED:
                continue
            assignment = SpeciesAssignment(evaluated, item.species, context, item.invasive, item.reasons)
            if assignment_rank(assignment) == BEST_ASSIGNMENT_RANK:
                return assignment
            if best is None or assignment_rank(assignment) < assignment_rank(best):
                best = assignment
        return best

    def _diversified(
        self, ranked: Sequence[RankedSpecies], target: str, usage: "_SpeciesUsage"
    ) -> list[RankedSpecies]:
        penalty = self._settings.diversity_penalty
        return sorted(
            ranked, key=lambda item: -(item.score - penalty * usage.share(target, item.species.key))
        )


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


class SpeciesSelectorFactory:
    def __init__(
        self,
        suitability: SpeciesSuitability,
        evaluator_factory: CandidateEvaluatorFactory,
        settings: SpeciesSettings,
    ) -> None:
        self._suitability = suitability
        self._evaluator_factory = evaluator_factory
        self._settings = settings

    @classmethod
    def from_knowledge(
        cls,
        knowledge_root: Path,
        settings: SpeciesSettings | None = None,
        design: DesignConstraints | None = None,
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
        return cls(SpeciesSuitability(catalog, registry, effective), evaluator_factory, effective)

    def for_site(self, site: SiteModel) -> SpeciesSelector:
        return SpeciesSelector(
            self._suitability,
            self._evaluator_factory.for_site(site),
            SiteContextDetector(site, self._settings),
            self._settings,
        )


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
