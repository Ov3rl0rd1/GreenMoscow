from dataclasses import dataclass, field
from typing import Any

TREE = "tree"
SHRUB = "shrub"
PLANT_TARGETS = (TREE, SHRUB)

PROHIBITIVE = "prohibitive"
CONDITIONAL = "conditional"
CONDITIONAL_MEASURE = "conditional_measure"
ADVISORY = "advisory"

DISTANCE_RULE = "distance"
ZONE_RULE = "zone"

SURFACE_MEASUREMENT = "network_surface"
STRUCTURE_EDGE_MEASUREMENT = "structure_edge"
GEOMETRY_MEASUREMENT = "geometry"

VERIFIED_STATUSES = frozenset({"verified", "verified_partial"})


@dataclass(frozen=True, slots=True)
class Citation:
    key: str
    doc_short: str
    locator: str
    verification: str
    doc_full: str = ""
    quote_ru: str = ""
    url: str = ""
    local_text: str = ""
    note: str = ""

    @property
    def is_verified(self) -> bool:
        return self.verification in VERIFIED_STATUSES


@dataclass(frozen=True, slots=True)
class CompetingValue:
    source_ref: str
    distance_m: float | None
    row_ru: str | None = None


@dataclass(frozen=True, slots=True)
class NormRule:
    rule_id: str
    rule_type: str
    obstacles: tuple[str, ...]
    targets: tuple[str, ...]
    severity: str
    distances: tuple[tuple[str, float | None], ...]
    zone_m: float | None
    zone_by_voltage: tuple[tuple[float, float], ...]
    measured_from: str
    source_refs: tuple[str, ...]
    competing: tuple[CompetingValue, ...]
    species_ru: tuple[str, ...]
    condition_ru: str
    rationale_ru: str
    is_assumption: bool
    parameters: dict[str, Any] = field(default_factory=dict)

    def distance_for(self, target: str) -> float | None:
        return next((distance for key, distance in self.distances if key == target), None)

    def applies_to(self, obstacle_kind: str, target: str) -> bool:
        return obstacle_kind in self.obstacles and target in self.targets


@dataclass(frozen=True, slots=True)
class Requirement:
    rule_id: str
    obstacle_kind: str
    target: str
    severity: str
    rule_type: str
    distance_m: float
    base_distance_m: float
    measurement_mode: str
    source_refs: tuple[str, ...]
    competing: tuple[CompetingValue, ...]
    crown_increment_m: float
    condition_ru: str
    is_assumption: bool

    @property
    def is_zone(self) -> bool:
        return self.rule_type == ZONE_RULE


@dataclass(frozen=True, slots=True)
class NormsDefaults:
    crown_base_diameter_m: float
    unknown_pipe_outer_diameter_m: float
    unknown_heating_channel_width_m: float
    trunk_diameter_at_planting_m: float
    crown_rule_source_ref: str = ""
