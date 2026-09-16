from collections.abc import Sequence

from shapely.strtree import STRtree

from greenplan.domain.decisions import ACCEPTED
from greenplan.domain.norms import (
    CONDITIONAL,
    CONDITIONAL_MEASURE,
    DISTANCE_RULE,
    NO_ACTIVATIONS,
    PROHIBITIVE,
    ROOT_BARRIER_RULE_SUFFIX,
    ROOT_BARRIERS_ACTIVATION,
    TREE,
    ZONE_RULE,
    NormRule,
)
from greenplan.domain.obstacle_kinds import HEATING_NETWORK
from greenplan.domain.site import Obstacle, SiteModel
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.verify.verification_model import (
    CONDITION_NOT_DECLARED,
    DECLARATION_SEVERITY,
    PlacedPlant,
    VerificationViolation,
)

MEASURED_FROM_NETWORK_SURFACE = "network_outer_surface"
MEASURED_FROM_STRUCTURE_EDGE = "zone_from_structure_edge"
CHECKED_SEVERITIES = frozenset({PROHIBITIVE, CONDITIONAL, CONDITIONAL_MEASURE})
CONDITION_SEVERITIES = frozenset({CONDITIONAL, CONDITIONAL_MEASURE})
MEASUREMENT_DECIMALS = 3


class IndependentNormChecker:
    def __init__(
        self,
        repository: NormsRepository,
        unknown_overhead_voltage_kv: float,
        tolerance_m: float,
        search_margin_m: float,
        active_activations: frozenset[str] = NO_ACTIVATIONS,
    ) -> None:
        self._defaults = repository.defaults
        self._reduced_distance_m = (
            repository.root_barrier.reduced_distance_m
            if repository.root_barrier is not None and ROOT_BARRIERS_ACTIVATION in active_activations
            else None
        )
        self._voltage_kv = unknown_overhead_voltage_kv
        self._tolerance_m = tolerance_m
        self._search_margin_m = search_margin_m
        self._rules = tuple(
            rule
            for rule in repository.rules()
            if rule.rule_type in (DISTANCE_RULE, ZONE_RULE)
            and rule.severity in CHECKED_SEVERITIES
            and not rule.species_ru
            and rule.is_active(active_activations)
        )
        self._largest_rule_distance_m = max(
            (self._base_distance(rule) or 0.0 for rule in self._rules), default=0.0
        )

    def violations(self, plants: Sequence[PlacedPlant], site: SiteModel) -> list[VerificationViolation]:
        obstacles = site.obstacles
        tree = STRtree([obstacle.geometry for obstacle in obstacles]) if obstacles else None
        if tree is None:
            return []
        return [violation for plant in plants for violation in self._plant_violations(plant, obstacles, tree)]

    def _plant_violations(
        self, plant: PlacedPlant, obstacles: Sequence[Obstacle], tree: STRtree
    ) -> list[VerificationViolation]:
        worst: dict[str, VerificationViolation] = {}
        inside_condition_zone = False
        for index in tree.query(plant.position, predicate="dwithin", distance=self._search_radius_m(plant)):
            obstacle = obstacles[int(index)]
            for rule in self._rules:
                if plant.plant_type not in rule.targets or obstacle.kind not in rule.obstacles:
                    continue
                required = self._required_distance(rule, plant)
                if required is None:
                    continue
                actual = self._measured_distance(plant, obstacle, rule.measured_from)
                if actual + self._tolerance_m >= required:
                    continue
                minimum = self._root_barrier_minimum(rule, plant, required)
                if rule.severity in CONDITION_SEVERITIES or (
                    minimum is not None and actual + self._tolerance_m >= minimum
                ):
                    inside_condition_zone = True
                    continue
                rule_id = rule.rule_id if minimum is None else rule.rule_id + ROOT_BARRIER_RULE_SUFFIX
                required = required if minimum is None else minimum
                candidate = VerificationViolation(
                    plant.plant_id,
                    rule_id,
                    PROHIBITIVE,
                    round(actual, MEASUREMENT_DECIMALS),
                    round(required, MEASUREMENT_DECIMALS),
                    obstacle.kind,
                )
                if rule_id not in worst or candidate.actual_m < worst[rule_id].actual_m:
                    worst[rule_id] = candidate
        found = list(worst.values())
        if inside_condition_zone and plant.status == ACCEPTED:
            found.append(VerificationViolation(plant.plant_id, CONDITION_NOT_DECLARED, DECLARATION_SEVERITY))
        return found

    def _root_barrier_minimum(self, rule: NormRule, plant: PlacedPlant, required: float) -> float | None:
        if (
            self._reduced_distance_m is None
            or not rule.root_barrier
            or rule.severity != PROHIBITIVE
            or plant.plant_type != TREE
            or required <= self._reduced_distance_m
        ):
            return None
        return self._reduced_distance_m

    def _search_radius_m(self, plant: PlacedPlant) -> float:
        return self._largest_rule_distance_m + self._crown_increment_m(plant) + self._search_margin_m

    def _required_distance(self, rule: NormRule, plant: PlacedPlant) -> float | None:
        if rule.rule_type == ZONE_RULE:
            return self._base_distance(rule)
        table_distance = rule.distance_for(plant.plant_type)
        if table_distance is None:
            return None
        if rule.severity == PROHIBITIVE and plant.plant_type == TREE and rule.crown_increment:
            return table_distance + self._crown_increment_m(plant)
        return table_distance

    def _base_distance(self, rule: NormRule) -> float | None:
        if rule.rule_type == DISTANCE_RULE:
            return max(
                (distance for _target, distance in rule.distances if distance is not None), default=None
            )
        if rule.zone_m is not None:
            return rule.zone_m
        return next((zone for max_kv, zone in rule.zone_by_voltage if self._voltage_kv <= max_kv), None)

    def _crown_increment_m(self, plant: PlacedPlant) -> float:
        if plant.plant_type != TREE:
            return 0.0
        return max(0.0, (plant.crown_diameter_m - self._defaults.crown_base_diameter_m) / 2)

    def _measured_distance(self, plant: PlacedPlant, obstacle: Obstacle, measured_from: str) -> float:
        axis_distance = plant.position.distance(obstacle.geometry)
        if measured_from == MEASURED_FROM_NETWORK_SURFACE:
            return (
                axis_distance
                - self._outer_radius_m(obstacle)
                - self._defaults.trunk_diameter_at_planting_m / 2
            )
        if measured_from == MEASURED_FROM_STRUCTURE_EDGE:
            return axis_distance - self._outer_radius_m(obstacle)
        return axis_distance

    def _outer_radius_m(self, obstacle: Obstacle) -> float:
        if obstacle.outer_radius_m is not None:
            return obstacle.outer_radius_m
        if obstacle.kind == HEATING_NETWORK:
            return self._defaults.unknown_heating_channel_width_m / 2
        return self._defaults.unknown_pipe_outer_diameter_m / 2
