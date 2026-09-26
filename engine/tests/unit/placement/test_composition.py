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
from greenplan.placement.composition_shapes import (
    EdgeLine,
    band_points,
    evenly_spaced,
    group_shape,
    hexagonal_patch,
    organic_mass,
)
from greenplan.placement.plant_placement_planner import guided_count, widened
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


def test_organic_mass_is_a_large_irregular_patch_with_the_shrub_spacing() -> None:
    mass = organic_mass(Point(0, 0), 5.0, 1.0, 0.0)
    assert 90 <= len(mass) <= 160
    assert min(first.distance(second) for first, second in combinations(mass, 2)) >= 1.0 - 1e-9
    xs = [point.x for point in mass]
    ys = [point.y for point in mass]
    assert max(xs) - min(xs) != pytest.approx(max(ys) - min(ys), abs=0.5)


def test_band_adds_staggered_rows_on_the_chosen_side() -> None:
    line = [Point(x, 0.0) for x in range(10)]
    band = band_points(line, 3, 1.0, 1.0)
    assert len(band) == 30
    assert all(point.y >= 0.0 for point in band)
    assert min(first.distance(second) for first, second in combinations(band, 2)) >= 1.0 - 1e-9


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


def test_shrubs_near_a_wide_edge_form_a_band_and_large_masses() -> None:
    composed = CompositionPlanner(CompositionSettings()).compose_shrubs(
        lawn_field(), accept_all(SHRUB), SHRUB, 1.0, 600
    )
    hedges = [element for element in composed.elements if element.kind == HEDGE]
    clumps = [element for element in composed.elements if element.kind == SHRUB_GROUP]
    assert hedges and max(element.size for element in hedges) >= 2 * CompositionSettings().hedge_min_size
    assert clumps and max(element.size for element in clumps) >= 40


def test_segments_split_where_the_row_is_interrupted() -> None:
    decisions = [accept_all(TREE)(Point(x, 0.0)) for x in (0.0, 6.0, 12.0, 30.0, 36.0)]
    assert [len(segment) for segment in contiguous(decisions, 9.0)] == [3, 2]


def test_density_cap_limits_the_model_unless_the_user_allows_exceeding_it() -> None:
    assert guided_count(529, 2766) == 529
    assert guided_count(529, 2766, respect_cap=False) == 2766
    assert guided_count(529, None, respect_cap=False) == 529
    assert guided_count(None, 40) == 40


def test_minimum_share_of_the_norm_lifts_a_too_shy_model() -> None:
    assert guided_count(274, 19, min_share=0.3) == 82
    assert guided_count(274, 19, respect_cap=False, min_share=0.3) == 82
    assert guided_count(274, 200, min_share=0.3) == 200
    assert guided_count(274, 400, min_share=0.3) == 274


def test_candidates_grow_by_score_when_they_cannot_hold_the_count() -> None:
    eligible = np.zeros((4, 4), dtype=bool)
    eligible[0, 0] = True
    pool = np.ones((4, 4), dtype=bool)
    pool[3, 3] = False
    score = np.arange(16, dtype=np.float32).reshape(4, 4)
    grown = widened(eligible, pool, score, 4)
    assert grown.sum() == 4 and grown[0, 0] and not grown[3, 3]
    assert grown[3, 2] and grown[3, 1] and grown[3, 0]
    assert widened(eligible, pool, score, 1) is eligible
