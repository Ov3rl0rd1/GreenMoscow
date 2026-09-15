from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, box

from greenplan.constraints.zone_builder import ZoneBuilder
from greenplan.domain.decisions import REJECTED, PlantCandidate
from greenplan.domain.norms import TREE

from fixtures.norms_factory import NormsToolkit, network, open_site


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


def test_prohibited_zone_width_includes_pipe_and_trunk_radii(toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (100, 0)], outer_radius_m=0.1)
    area = box(10, -20, 90, 20)
    zone = ZoneBuilder(toolkit.resolver, toolkit.meter).prohibited_zone([gas], TREE, 5.0, area)
    assert zone.area == pytest.approx(80 * 2 * (1.5 + 0.1 + 0.05), rel=1e-3)


def test_conditional_zone_uses_protection_zone_width(toolkit: NormsToolkit) -> None:
    gas = network("gas_pipeline", [(0, 0), (100, 0)], outer_radius_m=0.1)
    zone = ZoneBuilder(toolkit.resolver, toolkit.meter).conditional_zone(
        [gas], TREE, 5.0, box(10, -20, 90, 20)
    )
    assert zone.area == pytest.approx(80 * 2 * 2.0, rel=1e-3)


def test_zone_without_relevant_obstacles_is_empty(toolkit: NormsToolkit) -> None:
    assert (
        ZoneBuilder(toolkit.resolver, toolkit.meter).prohibited_zone([], TREE, 5.0, box(0, 0, 1, 1)).is_empty
    )


@settings(max_examples=60, deadline=None)
@given(offset=st.floats(min_value=0.2, max_value=3.0))
def test_vector_evaluation_agrees_with_prohibited_zone(toolkit: NormsToolkit, offset: float) -> None:
    gas = network("gas_pipeline", [(-100, 0), (100, 0)], outer_radius_m=0.1)
    zone = ZoneBuilder(toolkit.resolver, toolkit.meter).prohibited_zone(
        [gas], TREE, 5.0, box(-50, -10, 50, 10)
    )
    position = Point(0, offset)
    if abs(position.distance(zone.boundary)) < 0.01:
        return
    decision = toolkit.evaluator(open_site((gas,))).evaluate(PlantCandidate("T", position, TREE, 5.0))
    rejected_by_table = any(
        clearance.requirement.rule_id == "sp42_gas_tree" for clearance in decision.blocking_clearances
    )
    assert rejected_by_table == zone.contains(position)
    assert (decision.status == REJECTED) == rejected_by_table
