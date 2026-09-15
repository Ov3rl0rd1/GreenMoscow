from greenplan.domain.norms import (
    DISTANCE_RULE,
    GEOMETRY_MEASUREMENT,
    PROHIBITIVE,
    STRUCTURE_EDGE_MEASUREMENT,
    SURFACE_MEASUREMENT,
    TREE,
    ZONE_RULE,
    NormRule,
    Requirement,
)
from greenplan.knowledge.norms_repository import NormsRepository

MEASUREMENT_BY_MEASURED_FROM = {
    "network_outer_surface": SURFACE_MEASUREMENT,
    "zone_from_structure_edge": STRUCTURE_EDGE_MEASUREMENT,
}
EVALUATED_RULE_TYPES = frozenset({DISTANCE_RULE, ZONE_RULE})


class RequirementResolver:
    def __init__(self, repository: NormsRepository, unknown_overhead_voltage_kv: float) -> None:
        self._repository = repository
        self._unknown_overhead_voltage_kv = unknown_overhead_voltage_kv
        self._evaluated_rules = tuple(
            rule for rule in repository.rules() if rule.rule_type in EVALUATED_RULE_TYPES
        )
        self._requirements_cache: dict[tuple[str, str, float, str], tuple[Requirement, ...]] = {}
        self._max_distance_cache: dict[float, float] = {}

    def resolve(
        self, obstacle_kind: str, target: str, crown_diameter_m: float, species_name_ru: str | None = None
    ) -> tuple[Requirement, ...]:
        key = (obstacle_kind, target, round(crown_diameter_m, 3), normalize_species_name(species_name_ru))
        if key not in self._requirements_cache:
            self._requirements_cache[key] = tuple(
                self._requirement(rule, obstacle_kind, target, crown_diameter_m)
                for rule in self._evaluated_rules
                if rule.applies_to(obstacle_kind, target)
                and self._species_matches(rule, key[3])
                and self._base_distance(rule, target) is not None
            )
        return self._requirements_cache[key]

    def unregulated_rule_ids(self, obstacle_kind: str, target: str) -> tuple[str, ...]:
        return tuple(
            rule.rule_id
            for rule in self._evaluated_rules
            if rule.rule_type == DISTANCE_RULE
            and rule.applies_to(obstacle_kind, target)
            and rule.distance_for(target) is None
        )

    def max_requirement_distance_m(self, crown_diameter_m: float) -> float:
        key = round(crown_diameter_m, 3)
        if key not in self._max_distance_cache:
            self._max_distance_cache[key] = max(
                (
                    self._base_distance(rule, target) + self._crown_increment(rule, target, crown_diameter_m)
                    for rule in self._evaluated_rules
                    for target in rule.targets
                    if self._base_distance(rule, target) is not None
                ),
                default=0.0,
            )
        return self._max_distance_cache[key]

    def _base_distance(self, rule: NormRule, target: str) -> float | None:
        if rule.rule_type == DISTANCE_RULE:
            return rule.distance_for(target)
        if rule.zone_m is not None:
            return rule.zone_m
        return self._zone_for_voltage(rule)

    def _zone_for_voltage(self, rule: NormRule) -> float | None:
        applicable = [
            zone for max_kv, zone in rule.zone_by_voltage if self._unknown_overhead_voltage_kv <= max_kv
        ]
        return applicable[0] if applicable else None

    def _crown_increment(self, rule: NormRule, target: str, crown_diameter_m: float) -> float:
        if rule.rule_type != DISTANCE_RULE or rule.severity != PROHIBITIVE or target != TREE:
            return 0.0
        return max(0.0, (crown_diameter_m - self._repository.defaults.crown_base_diameter_m) / 2)

    def _species_matches(self, rule: NormRule, species_name: str) -> bool:
        if not rule.species_ru:
            return True
        return any(species_name.startswith(normalize_species_name(token)) for token in rule.species_ru)

    def _requirement(
        self, rule: NormRule, obstacle_kind: str, target: str, crown_diameter_m: float
    ) -> Requirement:
        base_distance = self._base_distance(rule, target)
        increment = self._crown_increment(rule, target, crown_diameter_m)
        return Requirement(
            rule_id=rule.rule_id,
            obstacle_kind=obstacle_kind,
            target=target,
            severity=rule.severity,
            rule_type=rule.rule_type,
            distance_m=base_distance + increment,
            base_distance_m=base_distance,
            measurement_mode=MEASUREMENT_BY_MEASURED_FROM.get(rule.measured_from, GEOMETRY_MEASUREMENT),
            source_refs=rule.source_refs,
            competing=rule.competing,
            crown_increment_m=increment,
            condition_ru=rule.condition_ru,
            is_assumption=rule.is_assumption,
        )


def normalize_species_name(name: str | None) -> str:
    return (name or "").strip().lower().replace("ё", "е")
