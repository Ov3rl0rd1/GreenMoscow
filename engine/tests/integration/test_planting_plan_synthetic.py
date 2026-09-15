from itertools import combinations
from pathlib import Path

import pytest

from greenplan.domain.decisions import REJECTED, primary_rejection_reason
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.planting_plan import PlantingPlan, PlantingPlanComposer

from fixtures.placement_factory import GAS_AXIS_Y, GAS_OUTER_RADIUS_M, KEPT_TREE, LAWN, POLE, street_site

TRUNK_RADIUS_M = 0.05
GAS_TABLE_DISTANCE_M = 1.5


@pytest.fixture(scope="module")
def plan(knowledge_root: Path) -> PlantingPlan:
    return PlantingPlanComposer.from_knowledge(knowledge_root).compose(street_site())


def positions(decisions):
    return [decision.candidate.position for decision in decisions]


def test_trees_fill_street_within_density_cap(plan: PlantingPlan) -> None:
    assert 10 <= len(plan.trees) <= plan.limits.max_trees == 18
    assert all(decision.is_placeable for decision in plan.trees)


def test_trees_keep_spacing_and_normative_clearances(plan: PlantingPlan) -> None:
    trees = positions(plan.trees)
    assert all(first.distance(second) >= 6.0 - 1e-9 for first, second in combinations(trees, 2))
    gas_limit = GAS_TABLE_DISTANCE_M + GAS_OUTER_RADIUS_M + TRUNK_RADIUS_M
    assert all(abs(tree.y - GAS_AXIS_Y) >= gas_limit for tree in trees)
    assert all(tree.distance(POLE) >= 4.0 for tree in trees)
    assert all(tree.distance(KEPT_TREE) >= 4.0 for tree in trees)
    assert all(LAWN.contains(tree) for tree in trees)


def test_first_tree_row_runs_along_carriageway(plan: PlantingPlan) -> None:
    roadside = [tree for tree in positions(plan.trees) if tree.y < GAS_AXIS_Y]
    assert len(roadside) >= 8


def test_shrubs_keep_spacing_and_distance_from_planned_trees(plan: PlantingPlan) -> None:
    shrubs = positions(plan.shrubs)
    trees = positions(plan.trees)
    assert 0 < len(shrubs) <= plan.limits.max_shrubs
    assert all(first.distance(second) >= 1.0 - 1e-9 for first, second in combinations(shrubs, 2))
    assert all(shrub.distance(tree) >= 1.5 for shrub in shrubs for tree in trees)


def test_rejections_carry_normative_reasons(plan: PlantingPlan) -> None:
    reasons = [primary_rejection_reason(decision) for decision in plan.rejections]
    assert plan.rejections
    assert all(decision.status == REJECTED for decision in plan.rejections)
    assert all(reasons)
    assert "sp42_gas_tree" in reasons
    assert (
        max(reasons.count(reason) for reason in set(reasons)) <= PlacementSettings().max_rejections_per_reason
    )


def test_identifiers_are_sequential(plan: PlantingPlan) -> None:
    assert plan.trees[0].candidate.candidate_id == "T-0001"
    assert plan.shrubs[-1].candidate.candidate_id == f"S-{len(plan.shrubs):04d}"
    assert plan.rejections[0].candidate.candidate_id == "R-0001"


def test_composition_is_deterministic(knowledge_root: Path, plan: PlantingPlan) -> None:
    again = PlantingPlanComposer.from_knowledge(knowledge_root).compose(street_site())
    assert [point.coords[0] for point in positions(again.trees)] == [
        point.coords[0] for point in positions(plan.trees)
    ]
