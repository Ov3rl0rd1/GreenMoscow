from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, box

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.zone_builder import ZoneBuilder
from greenplan.domain.decisions import REJECTED, PlantCandidate
from greenplan.domain.norms import TREE

from fixtures.norms_factory import NormsToolkit, network, open_site


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


def test_prohibited_zone_width_includes_pipe_and_trunk_radii(table_toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (100, 0)], outer_radius_m=0.1)
    area = box(10, -20, 90, 20)
    zone = ZoneBuilder(table_toolkit.resolver, table_toolkit.meter).prohibited_zone([gas], TREE, 5.0, area)
    assert zone.area == pytest.approx(80 * 2 * (1.5 + 0.1 + 0.05), rel=1e-3)


def test_conditional_zone_uses_protection_zone_width(zone_toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (100, 0)], outer_radius_m=0.1)
    zone = ZoneBuilder(zone_toolkit.resolver, zone_toolkit.meter).conditional_zone(
        [gas], TREE, 5.0, box(10, -20, 90, 20)
    )
    assert zone.area == pytest.approx(80 * 2 * 2.0, rel=1e-3)


def test_zone_without_relevant_obstacles_is_empty(toolkit: NormsToolkit) -> None:
    assert (
        ZoneBuilder(toolkit.resolver, toolkit.meter).prohibited_zone([], TREE, 5.0, box(0, 0, 1, 1)).is_empty
    )


@settings(max_examples=60, deadline=None)
@given(offset=st.floats(min_value=0.2, max_value=3.0))
def test_vector_evaluation_agrees_with_prohibited_zone(table_toolkit: NormsToolkit, offset: float) -> None:
    gas = network("gas_pipeline", [(-100, 0), (100, 0)], outer_radius_m=0.1)
    zone = ZoneBuilder(table_toolkit.resolver, table_toolkit.meter).prohibited_zone(
        [gas], TREE, 5.0, box(-50, -10, 50, 10)
    )
    position = Point(0, offset)
    if abs(position.distance(zone.boundary)) < 0.01:
        return
    decision = table_toolkit.evaluator(open_site((gas,))).evaluate(PlantCandidate("T", position, TREE, 5.0))
    rejected_by_table = any(
        clearance.requirement.rule_id == "sp42_gas_tree" for clearance in decision.blocking_clearances
    )
    assert rejected_by_table == zone.contains(position)
    assert (decision.status == REJECTED) == rejected_by_table


def test_conditional_zone_is_empty_without_protection_zones_and_barriers(table_toolkit: NormsToolkit) -> None:
    site = open_site((network("gas_pipeline", [(0, 0), (10, 0)], outer_radius_m=0.11),))
    builder = ZoneBuilder(table_toolkit.resolver, table_toolkit.meter)
    zone = builder.conditional_zone(site.obstacles, TREE, 5.0, box(-20, -20, 30, 20))
    assert zone.is_empty


def test_root_barrier_band_forms_the_conditional_zone(toolkit: NormsToolkit) -> None:
    site = open_site((network("gas_pipeline", [(0, 0), (10, 0)], outer_radius_m=0.11),))
    builder = ZoneBuilder(toolkit.resolver, toolkit.meter)
    area = box(-20, -20, 30, 20)
    prohibited = builder.prohibited_zone(site.obstacles, TREE, 5.0, area)
    conditional = builder.conditional_zone(site.obstacles, TREE, 5.0, area)
    assert prohibited.contains(Point(5, 1.1))
    assert not prohibited.contains(Point(5, 1.3))
    assert conditional.contains(Point(5, 1.3))
    assert not conditional.contains(Point(5, 1.8))
