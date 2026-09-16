from math import sqrt
from pathlib import Path

import pytest
from shapely.geometry import LineString, Point

from greenplan.constraints.root_barrier_planner import RootBarrierPlanner, total_length_m
from greenplan.domain.decisions import ACCEPTED, CONDITIONALLY_ACCEPTED, PlantCandidate
from greenplan.domain.norms import TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.domain.site import Obstacle
from greenplan.explain.explanation_builder import ExplanationBuilder

from fixtures.norms_factory import NormsToolkit, network, open_site

GAS_RADIUS_M = 0.055
TRUNK_RADIUS_M = 0.05


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


@pytest.fixture(scope="module")
def planner(toolkit: NormsToolkit) -> RootBarrierPlanner:
    return RootBarrierPlanner(toolkit.meter, toolkit.repository.root_barrier.network_to_barrier_m)


def tree_at(x: float, y: float) -> PlantCandidate:
    return PlantCandidate("T-1", Point(x, y), TREE, 5.0)


def gas_site():
    return open_site((network("gas_pipeline", [(-50, 0), (50, 0)], outer_radius_m=GAS_RADIUS_M),))


def test_barrier_runs_along_the_pipe_between_pipe_and_trunk(toolkit, planner) -> None:
    decision = toolkit.evaluator(gas_site()).evaluate(tree_at(0, 1.55))
    assert decision.status == CONDITIONALLY_ACCEPTED
    barriers = planner.barriers(decision)
    assert len(barriers) == 1
    line = barriers[0].line
    assert all(y == pytest.approx(GAS_RADIUS_M + 0.5) for _x, y in line.coords)
    assert barriers[0].rule_id == "sp42_gas_tree"


def test_barrier_covers_the_stretch_closer_than_the_norm(toolkit, planner) -> None:
    decision = toolkit.evaluator(gas_site()).evaluate(tree_at(0, 1.55))
    reach = 1.5 + GAS_RADIUS_M + TRUNK_RADIUS_M
    expected = 2 * sqrt(reach**2 - 1.55**2)
    assert total_length_m(planner.barriers(decision)) == pytest.approx(expected, rel=2e-3)


def test_accepted_tree_needs_no_barrier(toolkit, planner) -> None:
    decision = toolkit.evaluator(gas_site()).evaluate(tree_at(0, 3.0))
    assert decision.status == ACCEPTED
    assert planner.barriers(decision) == ()


def test_curb_barrier_is_half_a_metre_from_the_edge(toolkit, planner) -> None:
    edge = Obstacle(CARRIAGEWAY_EDGE, LineString([(-50, 0), (50, 0)]), "curb", "surfaces", ("surface",))
    decision = toolkit.evaluator(open_site((edge,))).evaluate(tree_at(0, 1.5))
    assert decision.status == CONDITIONALLY_ACCEPTED
    barriers = planner.barriers(decision)
    assert barriers
    assert all(y == pytest.approx(0.5) for barrier in barriers for _x, y in barrier.line.coords)


def test_explanation_names_the_measure_and_the_barrier_length(knowledge_root: Path, toolkit) -> None:
    builder = ExplanationBuilder.from_knowledge(knowledge_root)
    explanation = builder.for_decision(toolkit.evaluator(gas_site()).evaluate(tree_at(0, 1.55)))
    assert explanation.root_barrier_length_m > 0
    assert explanation.root_barriers
    assert "только при условии" in explanation.explanation_ru
    assert "Корнезащита вдоль сети" in explanation.explanation_ru


def test_rejection_below_the_minimum_says_barrier_does_not_help(knowledge_root: Path, toolkit) -> None:
    builder = ExplanationBuilder.from_knowledge(knowledge_root)
    explanation = builder.for_decision(toolkit.evaluator(gas_site()).evaluate(tree_at(0, 1.1)))
    assert "даже при устройстве корнезащиты" in explanation.explanation_ru
    assert explanation.root_barriers == ()
