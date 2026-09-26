import pytest
from shapely.strtree import STRtree

from greenplan.domain.decisions import primary_rejection_reason
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.domain.site import SiteModel
from greenplan.placement.planting_plan import PlantingPlan

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


def test_trees_are_planted_near_carriageway(
    bagritskogo_plan: PlantingPlan, bagritskogo_site: SiteModel
) -> None:
    edges = [edge.geometry for edge in bagritskogo_site.obstacles_of(CARRIAGEWAY_EDGE)]
    tree = STRtree(edges)
    distances = [
        edges[int(tree.nearest(decision.candidate.position))].distance(decision.candidate.position)
        for decision in bagritskogo_plan.trees
    ]
    assert len(bagritskogo_plan.trees) > 20
    assert sum(1 for distance in distances if distance <= 6.0) >= 0.4 * len(distances)


def test_all_plants_are_placeable_and_within_caps(bagritskogo_plan: PlantingPlan) -> None:
    limits = bagritskogo_plan.limits
    assert all(decision.is_placeable for decision in bagritskogo_plan.trees + bagritskogo_plan.shrubs)
    assert len(bagritskogo_plan.trees) <= limits.max_trees
    assert len(bagritskogo_plan.shrubs) <= limits.max_shrubs


def test_trees_keep_minimum_spacing(bagritskogo_plan: PlantingPlan) -> None:
    positions = [decision.candidate.position for decision in bagritskogo_plan.trees]
    index = STRtree(positions)
    spacing = bagritskogo_plan.limits.tree_spacing_m
    for number, position in enumerate(positions):
        neighbours = index.query(position, predicate="dwithin", distance=spacing - 1e-6)
        assert set(neighbours.tolist()) == {number}


def test_rejections_have_reasons(bagritskogo_plan: PlantingPlan) -> None:
    assert bagritskogo_plan.rejections
    assert all(primary_rejection_reason(decision) for decision in bagritskogo_plan.rejections)
