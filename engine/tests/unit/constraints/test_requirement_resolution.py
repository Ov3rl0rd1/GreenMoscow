from pathlib import Path

import pytest
from shapely.geometry import Point

from greenplan.domain.norms import ADVISORY, CONDITIONAL, PROHIBITIVE, SHRUB, TREE

from fixtures.norms_factory import NormsToolkit, network


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


def by_severity(requirements) -> dict[str, float]:
    result: dict[str, float] = {}
    for requirement in requirements:
        result[requirement.severity] = max(result.get(requirement.severity, 0.0), requirement.distance_m)
    return result


def test_gas_pipeline_tree_has_prohibitive_table_distance_and_conditional_zone(toolkit: NormsToolkit) -> None:
    distances = by_severity(toolkit.resolver.resolve("gas_pipeline", TREE, crown_diameter_m=5.0))
    assert distances[PROHIBITIVE] == pytest.approx(1.5)
    assert distances[CONDITIONAL] == pytest.approx(2.0)


def test_unregulated_shrub_distance_is_not_a_zero_requirement(toolkit: NormsToolkit) -> None:
    requirements = toolkit.resolver.resolve("gas_pipeline", SHRUB, crown_diameter_m=2.0)
    assert all(requirement.severity != PROHIBITIVE for requirement in requirements)
    assert "sp42_gas_shrub" in toolkit.resolver.unregulated_rule_ids("gas_pipeline", SHRUB)


def test_maximum_is_taken_within_severity_for_heating_network(toolkit: NormsToolkit) -> None:
    distances = by_severity(toolkit.resolver.resolve("heating_network", TREE, crown_diameter_m=5.0))
    assert distances[PROHIBITIVE] == pytest.approx(2.0)
    assert distances[CONDITIONAL] == pytest.approx(3.0)


def test_large_crown_increases_prohibitive_table_distance(toolkit: NormsToolkit) -> None:
    requirements = toolkit.resolver.resolve("water_supply", TREE, crown_diameter_m=9.0)
    prohibitive = [requirement for requirement in requirements if requirement.severity == PROHIBITIVE]
    assert prohibitive[0].distance_m == pytest.approx(4.0)
    assert prohibitive[0].crown_increment_m == pytest.approx(2.0)


def test_crown_increment_does_not_change_protection_zones(toolkit: NormsToolkit) -> None:
    distances = by_severity(toolkit.resolver.resolve("gas_pipeline", TREE, crown_diameter_m=9.0))
    assert distances[CONDITIONAL] == pytest.approx(2.0)


def test_species_specific_heating_advisory_applies_only_to_listed_species(toolkit: NormsToolkit) -> None:
    for_lime = by_severity(toolkit.resolver.resolve("heating_network", TREE, 5.0, "Липа мелколистная"))
    for_dogwood = by_severity(toolkit.resolver.resolve("heating_network", SHRUB, 2.0, "Дёрен белый"))
    for_spiraea = by_severity(toolkit.resolver.resolve("heating_network", SHRUB, 1.5, "Спирея Вангутта"))
    assert for_lime[ADVISORY] == pytest.approx(2.0)
    assert for_dogwood[ADVISORY] == pytest.approx(4.0)
    assert ADVISORY not in for_spiraea


def test_unknown_overhead_voltage_uses_configured_class(toolkit: NormsToolkit) -> None:
    distances = by_severity(toolkit.resolver.resolve("overhead_line", TREE, 5.0))
    assert distances[CONDITIONAL] == pytest.approx(10.0)


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


def test_zone_is_measured_from_axis(toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (10, 0)], outer_radius_m=0.11)
    zone = next(
        item for item in toolkit.resolver.resolve("gas_pipeline", TREE, 5.0) if item.severity == CONDITIONAL
    )
    assert toolkit.meter.measure(Point(5, 1.8), gas, zone).actual_m == pytest.approx(1.8)
