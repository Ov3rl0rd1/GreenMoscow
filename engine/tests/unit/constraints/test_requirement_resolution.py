from pathlib import Path

import pytest
from shapely.geometry import Point

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.domain.norms import ADVISORY, CONDITIONAL, CONDITIONAL_MEASURE, PROHIBITIVE, SHRUB, TREE

from fixtures.norms_factory import NormsToolkit, network


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


@pytest.fixture(scope="module")
def table_toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root, DesignConstraints(allow_root_barriers=False))


@pytest.fixture(scope="module")
def zone_toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(
        knowledge_root, DesignConstraints(apply_protection_zones=True, allow_root_barriers=False)
    )


def by_severity(requirements) -> dict[str, float]:
    result: dict[str, float] = {}
    for requirement in requirements:
        result[requirement.severity] = max(result.get(requirement.severity, 0.0), requirement.distance_m)
    return result


def test_gas_pipeline_tree_has_prohibitive_table_distance_and_conditional_zone(
    zone_toolkit: NormsToolkit,
) -> None:
    distances = by_severity(zone_toolkit.resolver.resolve("gas_pipeline", TREE, crown_diameter_m=5.0))
    assert distances[PROHIBITIVE] == pytest.approx(1.5)
    assert distances[CONDITIONAL] == pytest.approx(2.0)


def test_unregulated_shrub_distance_is_not_a_zero_requirement(toolkit: NormsToolkit) -> None:
    requirements = toolkit.resolver.resolve("gas_pipeline", SHRUB, crown_diameter_m=2.0)
    assert all(requirement.severity != PROHIBITIVE for requirement in requirements)
    assert "sp42_gas_shrub" in toolkit.resolver.unregulated_rule_ids("gas_pipeline", SHRUB)


def test_maximum_is_taken_within_severity_for_heating_network(zone_toolkit: NormsToolkit) -> None:
    distances = by_severity(zone_toolkit.resolver.resolve("heating_network", TREE, crown_diameter_m=5.0))
    assert distances[PROHIBITIVE] == pytest.approx(2.0)
    assert distances[CONDITIONAL] == pytest.approx(3.0)


def test_large_crown_increases_prohibitive_table_distance(table_toolkit: NormsToolkit) -> None:
    requirements = table_toolkit.resolver.resolve("water_supply", TREE, crown_diameter_m=9.0)
    prohibitive = [requirement for requirement in requirements if requirement.severity == PROHIBITIVE]
    assert prohibitive[0].distance_m == pytest.approx(4.0)
    assert prohibitive[0].crown_increment_m == pytest.approx(2.0)


def test_crown_increment_does_not_change_protection_zones(zone_toolkit: NormsToolkit) -> None:
    distances = by_severity(zone_toolkit.resolver.resolve("gas_pipeline", TREE, crown_diameter_m=9.0))
    assert distances[CONDITIONAL] == pytest.approx(2.0)


def test_species_specific_heating_advisory_applies_only_to_listed_species(toolkit: NormsToolkit) -> None:
    for_lime = by_severity(toolkit.resolver.resolve("heating_network", TREE, 5.0, "Липа мелколистная"))
    for_dogwood = by_severity(toolkit.resolver.resolve("heating_network", SHRUB, 2.0, "Дёрен белый"))
    for_spiraea = by_severity(toolkit.resolver.resolve("heating_network", SHRUB, 1.5, "Спирея Вангутта"))
    assert for_lime[ADVISORY] == pytest.approx(2.0)
    assert for_dogwood[ADVISORY] == pytest.approx(4.0)
    assert ADVISORY not in for_spiraea


def test_unknown_overhead_voltage_uses_configured_class(zone_toolkit: NormsToolkit) -> None:
    distances = by_severity(zone_toolkit.resolver.resolve("overhead_line", TREE, 5.0))
    assert distances[CONDITIONAL] == pytest.approx(10.0)


def test_overhead_line_distance_is_measured_to_the_crown_edge(toolkit: NormsToolkit) -> None:
    line = network("overhead_line", [(0, 0), (10, 0)])
    requirement = next(
        item for item in toolkit.resolver.resolve("overhead_line", TREE, 6.0) if item.severity == PROHIBITIVE
    )
    assert requirement.distance_m == pytest.approx(3.0)
    assert requirement.crown_increment_m == 0.0
    assert toolkit.meter.measure(Point(5, 5.0), line, requirement).actual_m == pytest.approx(2.0)
    assert toolkit.meter.geometry_offset_m(line, requirement) == pytest.approx(6.0)
    assert toolkit.resolver.max_requirement_distance_m(6.0) >= 6.0
    assert requirement.voltage_kv == pytest.approx(10.0)


def test_surface_measurement_subtracts_pipe_and_trunk_radii(toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (10, 0)], outer_radius_m=0.11)
    requirement = next(
        item for item in toolkit.resolver.resolve("gas_pipeline", TREE, 5.0) if item.severity == PROHIBITIVE
    )
    measured = toolkit.meter.measure(Point(5, 2.0), gas, requirement)
    assert measured.actual_m == pytest.approx(2.0 - 0.11 - 0.05)
    assert not measured.assumed_outer_radius


def test_unknown_pipe_radius_is_assumed_conservatively(toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (10, 0)])
    requirement = next(
        item for item in toolkit.resolver.resolve("gas_pipeline", TREE, 5.0) if item.severity == PROHIBITIVE
    )
    measured = toolkit.meter.measure(Point(5, 2.0), gas, requirement)
    assert measured.actual_m == pytest.approx(2.0 - 0.25 - 0.05)
    assert measured.assumed_outer_radius


def test_zone_is_measured_from_axis(zone_toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (10, 0)], outer_radius_m=0.11)
    zone = next(
        item
        for item in zone_toolkit.resolver.resolve("gas_pipeline", TREE, 5.0)
        if item.severity == CONDITIONAL
    )
    assert zone_toolkit.meter.measure(Point(5, 1.8), gas, zone).actual_m == pytest.approx(1.8)


@pytest.mark.parametrize(
    "obstacle", ["gas_pipeline", "heating_network", "power_cable", "communication_cable", "overhead_line"]
)
def test_protection_zones_are_not_resolved_by_default(toolkit: NormsToolkit, obstacle: str) -> None:
    for target in (TREE, SHRUB):
        severities = {item.severity for item in toolkit.resolver.resolve(obstacle, target, 5.0)}
        assert CONDITIONAL not in severities


def test_gas_pipeline_tree_keeps_only_the_table_distance_without_barriers(
    table_toolkit: NormsToolkit,
) -> None:
    distances = by_severity(table_toolkit.resolver.resolve("gas_pipeline", TREE, crown_diameter_m=5.0))
    assert distances == {PROHIBITIVE: pytest.approx(1.5)}


def test_root_barrier_splits_table_distance_into_minimum_and_measure_band(toolkit: NormsToolkit) -> None:
    requirements = toolkit.resolver.resolve("gas_pipeline", TREE, crown_diameter_m=5.0)
    by_rule = {item.rule_id: item for item in requirements}
    assert by_rule["sp42_gas_tree_root_barrier"].severity == PROHIBITIVE
    assert by_rule["sp42_gas_tree_root_barrier"].distance_m == pytest.approx(1.0)
    assert by_rule["sp42_gas_tree"].severity == CONDITIONAL_MEASURE
    assert by_rule["sp42_gas_tree"].distance_m == pytest.approx(1.5)


def test_barrier_band_keeps_the_crown_increment(toolkit: NormsToolkit) -> None:
    requirements = toolkit.resolver.resolve("water_supply", TREE, crown_diameter_m=9.0)
    by_rule = {item.rule_id: item for item in requirements}
    assert by_rule["sp42_water_tree"].distance_m == pytest.approx(4.0)
    assert by_rule["sp42_water_tree_root_barrier"].distance_m == pytest.approx(1.0)
    assert by_rule["sp42_water_tree_root_barrier"].crown_increment_m == 0.0


def test_shrub_requirements_are_not_split(toolkit: NormsToolkit) -> None:
    severities = {item.severity for item in toolkit.resolver.resolve("power_cable", SHRUB, 1.5)}
    assert severities == {PROHIBITIVE}


def test_table_distance_not_above_the_minimum_is_not_split(toolkit: NormsToolkit) -> None:
    requirements = toolkit.resolver.resolve("lks_tmk", TREE, crown_diameter_m=5.0)
    assert [(item.rule_id, item.severity) for item in requirements] == [("sp42_lks_tmk_tree", PROHIBITIVE)]


def test_snow_buffer_bounds_the_curb_reduction_without_crown_increment(toolkit: NormsToolkit) -> None:
    requirements = toolkit.resolver.resolve("carriageway_edge", TREE, crown_diameter_m=9.0)
    by_rule = {item.rule_id: item for item in requirements}
    assert by_rule["design_snow_buffer_carriageway"].distance_m == pytest.approx(1.0)
    assert by_rule["design_snow_buffer_carriageway"].crown_increment_m == 0.0
    assert by_rule["sp42_carriageway_tree"].severity == CONDITIONAL_MEASURE
    assert by_rule["sp42_carriageway_tree"].distance_m == pytest.approx(4.0)


def test_snow_buffer_applies_to_shrubs(toolkit: NormsToolkit) -> None:
    rules = {item.rule_id for item in toolkit.resolver.resolve("carriageway_edge", SHRUB, 1.5)}
    assert "design_snow_buffer_carriageway" in rules
