import numpy as np
from shapely.geometry import LineString, Point, box

from greenplan.domain.composition import GROUP, SHRUB_GROUP, CompositionElement
from greenplan.domain.decisions import ACCEPTED, PlantCandidate, PlantingDecision
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.domain.site import Obstacle, SiteDiagnostics, SiteModel
from greenplan.placement.composition_planner import CompositionField
from greenplan.placement.composition_settings import CompositionSettings
from greenplan.placement.composition_shapes import lawn_edges
from greenplan.placement.design_coordinator import DesignCoordinator, TargetContext
from greenplan.placement.design_review import (
    BARE_TREE_GROUP,
    EMPTY_LAWN,
    UNSHELTERED_FRONT,
    DesignReviewer,
    PlanSnapshot,
)
from greenplan.placement.raster import RasterGrid

LAWN = box(0.0, 0.0, 90.0, 40.0)
ROAD = Obstacle(CARRIAGEWAY_EDGE, LineString([(0.0, -2.0), (90.0, -2.0)]), "road", "surfaces", ("surface",))


def site() -> SiteModel:
    return SiteModel(LAWN, LAWN, (ROAD,), (), (), SiteDiagnostics())


def planted(target: str, x: float, y: float, element_id: str = "") -> PlantingDecision:
    crown = 5.0 if target == TREE else 1.5
    return PlantingDecision(
        PlantCandidate("", Point(x, y), target, crown, element_id=element_id), ACCEPTED, (), ()
    )


def accept(target: str):
    return lambda point: planted(target, point.x, point.y)


def field() -> CompositionField:
    grid = RasterGrid.covering(LAWN.bounds, 0.5)
    xs, ys = grid.cell_centers()
    inside = (xs > 0) & (xs < 90) & (ys > 0) & (ys < 40)
    clearance = np.minimum.reduce([ys, 40 - ys, xs, 90 - xs]).astype(np.float32)
    return CompositionField(
        grid, np.where(inside, 1.0, 0.0).astype(np.float32), inside, clearance, tuple(lawn_edges(LAWN, 0.5))
    )


def test_reviewer_finds_empty_lawn_bare_groups_and_unsheltered_front() -> None:
    group = [planted(TREE, x, 30.0, "tree-group-001") for x in (70.0, 76.0, 73.0)]
    snapshot = PlanSnapshot(group, [], [CompositionElement("tree-group-001", GROUP, TREE, 3, 6.0)])
    kinds = {problem.kind for problem in DesignReviewer().review(site(), snapshot)}
    assert {EMPTY_LAWN, BARE_TREE_GROUP, UNSHELTERED_FRONT} <= kinds


def test_coordinator_fills_empty_lawn_with_groups_and_clumps_within_its_budget() -> None:
    coordinator = DesignCoordinator(DesignReviewer(), CompositionSettings())
    snapshot = PlanSnapshot([], [], [])
    result = coordinator.improve(
        site(),
        snapshot,
        TargetContext(field(), accept(TREE), 5.0, 12),
        TargetContext(field(), accept(SHRUB), 1.0, 60),
        1.5,
    )
    assert 0 < len(result.trees) <= 12
    assert 0 < len(result.shrubs) <= 60
    assert {element.kind for element in result.elements} & {GROUP, SHRUB_GROUP}
    assert result.journal
    assert all(entry.planted > 0 for entry in result.journal)
    trees = [decision.candidate.position for decision in result.trees]
    shrubs = [decision.candidate.position for decision in result.shrubs]
    assert all(shrub.distance(tree) >= 1.5 for shrub in shrubs for tree in trees)


def test_coordinator_does_nothing_without_budget() -> None:
    coordinator = DesignCoordinator(DesignReviewer(), CompositionSettings())
    result = coordinator.improve(
        site(),
        PlanSnapshot([], [], []),
        TargetContext(field(), accept(TREE), 5.0, 0),
        TargetContext(field(), accept(SHRUB), 1.0, 0),
        1.5,
    )
    assert result.trees == () and result.shrubs == () and result.journal == ()
