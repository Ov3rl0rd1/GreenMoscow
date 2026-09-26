from itertools import combinations

import numpy as np
import pytest
from shapely.geometry import LineString, Point, box

from greenplan.domain.composition import GROUP, HEDGE, ROW, SHRUB_GROUP, SOLITARY
from greenplan.domain.decisions import ACCEPTED, PlantCandidate, PlantingDecision
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.placement.composition_planner import CompositionField, CompositionPlanner, contiguous
from greenplan.placement.composition_settings import CompositionSettings
from greenplan.placement.composition_shapes import EdgeLine, evenly_spaced, group_shape, hexagonal_patch
from greenplan.placement.raster import RasterGrid

CELL = 0.5
LAWN = box(0.0, 0.0, 120.0, 40.0)
EDGE = EdgeLine(LineString([(0.0, 0.0), (120.0, 0.0)]), CARRIAGEWAY_EDGE)


def lawn_field(lawn=LAWN, edges=(EDGE,)) -> CompositionField:
    min_x, min_y, max_x, max_y = lawn.bounds
    grid = RasterGrid.covering((min_x, min_y, max_x, max_y), CELL)
    xs, ys = grid.cell_centers()
    eligible = np.array(
        [
            [lawn.contains(Point(x, y)) for x, y in zip(row_x, row_y, strict=True)]
            for row_x, row_y in zip(xs, ys, strict=True)
        ]
    )
    clearance = np.minimum.reduce([ys - min_y, max_y - ys, xs - min_x, max_x - xs]).astype(np.float32)
    score = np.where(eligible, 1.0 - np.abs(ys - 3.0) / 100.0, 0.0).astype(np.float32)
    return CompositionField(grid, score, eligible, clearance, tuple(edges))


def accept_all(target: str):
    def trial(point: Point) -> PlantingDecision:
        return PlantingDecision(PlantCandidate("", point, target, 5.0), ACCEPTED, (), ())

    return trial


def positions(composed) -> list[Point]:
    return [decision.candidate.position for decision in composed.decisions]


def test_row_points_are_evenly_spaced_along_the_line() -> None:
    points = evenly_spaced(LineString([(0, 0), (20, 0)]), 6.0)
    assert [round(point.x, 3) for point in points] == [1.0, 7.0, 13.0, 19.0]


def test_group_shape_keeps_the_spacing_between_neighbours() -> None:
    shape = group_shape(Point(0, 0), 5, 6.0, 0.3)
    sides = [shape[index].distance(shape[(index + 1) % 5]) for index in range(5)]
    assert sides == pytest.approx([6.0] * 5)


def test_hexagonal_patch_sizes() -> None:
    assert len(hexagonal_patch(Point(0, 0), 1, 1.0)) == 7
    assert len(hexagonal_patch(Point(0, 0), 2, 1.0)) == 19


def test_trees_form_a_row_along_the_road_then_groups_within_budget() -> None:
    composed = CompositionPlanner(CompositionSettings()).compose_trees(
        lawn_field(), accept_all(TREE), TREE, 5.0, 30
    )
    kinds = [element.kind for element in composed.elements]
    rows = [element for element in composed.elements if element.kind == ROW]
    assert kinds[0] == ROW
    assert rows[0].edge_kind == CARRIAGEWAY_EDGE and rows[0].size >= 10
    assert GROUP in kinds
    assert len(composed.decisions) <= 30
    placed = positions(composed)
    assert all(first.distance(second) >= 5.0 - 1e-9 for first, second in combinations(placed, 2))
    assert {decision.candidate.element_id for decision in composed.decisions} == {
        element.element_id for element in composed.elements
    }


def test_row_share_leaves_budget_for_groups_and_solitaires() -> None:
    settings = CompositionSettings(tree_row_budget_share=0.3)
    composed = CompositionPlanner(settings).compose_trees(lawn_field(), accept_all(TREE), TREE, 5.0, 20)
    in_rows = sum(element.size for element in composed.elements if element.kind == ROW)
    assert in_rows <= 6
    assert {GROUP, SOLITARY} & {element.kind for element in composed.elements}


def test_fragments_rejected_by_norms_do_not_become_elements() -> None:
    def near_road_only(point: Point) -> PlantingDecision | None:
        return accept_all(TREE)(point) if point.x < 8.0 else None

    composed = CompositionPlanner(CompositionSettings()).compose_trees(
        lawn_field(), near_road_only, TREE, 5.0, 10
    )
    assert all(element.kind != ROW for element in composed.elements)


def test_shrubs_become_hedges_along_the_edge_and_compact_groups() -> None:
    composed = CompositionPlanner(CompositionSettings()).compose_shrubs(
        lawn_field(), accept_all(SHRUB), SHRUB, 1.0, 200
    )
    kinds = {element.kind for element in composed.elements}
    assert {HEDGE, SHRUB_GROUP} <= kinds
    hedge = next(element for element in composed.elements if element.kind == HEDGE)
    assert hedge.size >= CompositionSettings().hedge_min_size


def test_segments_split_where_the_row_is_interrupted() -> None:
    decisions = [accept_all(TREE)(Point(x, 0.0)) for x in (0.0, 6.0, 12.0, 30.0, 36.0)]
    assert [len(segment) for segment in contiguous(decisions, 9.0)] == [3, 2]
