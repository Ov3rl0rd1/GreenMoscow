from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from shapely.geometry import Point

from greenplan.domain.norms import ADVISORY, CONDITIONAL, CONDITIONAL_MEASURE, PROHIBITIVE, Requirement
from greenplan.domain.site import Obstacle

ACCEPTED = "accepted"
CONDITIONALLY_ACCEPTED = "conditional"
REJECTED = "rejected"

OUTSIDE_PLANTABLE_SURFACE = "outside_plantable_surface"
OUTSIDE_SITE_BOUNDARY = "outside_site_boundary"
TOO_CLOSE_TO_EXISTING_TREE = "too_close_to_existing_tree"
TOO_CLOSE_TO_PLANNED_PLANT = "too_close_to_planned_plant"

BLOCKING_SEVERITIES = frozenset({PROHIBITIVE})
CONDITION_SEVERITIES = frozenset({CONDITIONAL, CONDITIONAL_MEASURE})
ADVISORY_SEVERITIES = frozenset({ADVISORY})


@dataclass(frozen=True, slots=True)
class PlantCandidate:
    candidate_id: str
    position: Point
    target: str
    crown_diameter_m: float
    species_key: str | None = None
    species_name_ru: str | None = None


@dataclass(frozen=True, slots=True)
class Clearance:
    obstacle: Obstacle
    requirement: Requirement
    actual_m: float
    satisfied: bool
    assumed_outer_radius: bool

    @property
    def margin_m(self) -> float:
        return self.actual_m - self.requirement.distance_m


@dataclass(frozen=True, slots=True)
class SiteViolation:
    code: str
    actual_m: float | None = None
    required_m: float | None = None


@dataclass(frozen=True, slots=True)
class PlantingDecision:
    candidate: PlantCandidate
    status: str
    clearances: tuple[Clearance, ...]
    site_violations: tuple[SiteViolation, ...]

    @property
    def blocking_clearances(self) -> tuple[Clearance, ...]:
        return unsatisfied_with_severity(self.clearances, BLOCKING_SEVERITIES)

    @property
    def condition_clearances(self) -> tuple[Clearance, ...]:
        return unsatisfied_with_severity(self.clearances, CONDITION_SEVERITIES)

    @property
    def advisory_clearances(self) -> tuple[Clearance, ...]:
        return unsatisfied_with_severity(self.clearances, ADVISORY_SEVERITIES)

    @property
    def is_placeable(self) -> bool:
        return self.status != REJECTED


def unsatisfied_with_severity(
    clearances: Iterable[Clearance], severities: frozenset[str]
) -> tuple[Clearance, ...]:
    return tuple(
        clearance
        for clearance in clearances
        if not clearance.satisfied and clearance.requirement.severity in severities
    )


def decision_status(clearances: Sequence[Clearance], site_violations: Sequence[SiteViolation]) -> str:
    if site_violations or unsatisfied_with_severity(clearances, BLOCKING_SEVERITIES):
        return REJECTED
    if unsatisfied_with_severity(clearances, CONDITION_SEVERITIES):
        return CONDITIONALLY_ACCEPTED
    return ACCEPTED
