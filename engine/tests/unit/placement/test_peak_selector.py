from itertools import combinations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from greenplan.placement.peak_selector import PeakSelector
from greenplan.placement.raster import RasterGrid

SELECTOR = PeakSelector()


@st.composite
def score_fields(draw) -> tuple[RasterGrid, np.ndarray, np.ndarray]:
    rows = draw(st.integers(min_value=1, max_value=20))
    columns = draw(st.integers(min_value=1, max_value=20))
    size = rows * columns
    scores = draw(st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=size, max_size=size))
    eligible = draw(st.lists(st.booleans(), min_size=size, max_size=size))
    cell_size = draw(st.sampled_from([0.25, 0.5, 1.0]))
    grid = RasterGrid(0.0, 0.0, cell_size, rows, columns)
    return grid, np.array(scores).reshape(rows, columns), np.array(eligible).reshape(rows, columns)


@settings(max_examples=120, deadline=None)
@given(score_field=score_fields(), spacing=st.floats(min_value=0.3, max_value=6.0))
def test_no_two_selected_points_are_closer_than_spacing(score_field, spacing: float) -> None:
    grid, scores, eligible = score_field
    points = SELECTOR.select(grid, scores, eligible, spacing, None)
    assert all(first.distance(second) >= spacing - 1e-9 for first, second in combinations(points, 2))
    assert all(eligible[grid.cell_of(point.x, point.y)] for point in points)


def test_highest_scores_are_taken_first() -> None:
    grid = RasterGrid(0.0, 0.0, 1.0, 1, 5)
    scores = np.array([[0.1, 0.9, 0.3, 0.95, 0.2]])
    points = SELECTOR.select(grid, scores, np.ones((1, 5), dtype=bool), 1.5, None)
    assert [point.x for point in points] == [3.5, 1.5]


def test_max_count_limits_selection() -> None:
    grid = RasterGrid(0.0, 0.0, 1.0, 1, 10)
    scores = np.arange(10, dtype=float).reshape(1, 10)
    assert len(SELECTOR.select(grid, scores, np.ones((1, 10), dtype=bool), 1.0, 3)) == 3


def test_refused_point_does_not_block_its_neighbours() -> None:
    grid = RasterGrid(0.0, 0.0, 1.0, 1, 3)
    scores = np.array([[0.5, 1.0, 0.4]])
    points = SELECTOR.select(
        grid, scores, np.ones((1, 3), dtype=bool), 1.5, None, lambda point: point.x != 1.5
    )
    assert [point.x for point in points] == [0.5, 2.5]


def test_nothing_eligible_selects_nothing() -> None:
    grid = RasterGrid(0.0, 0.0, 1.0, 2, 2)
    assert SELECTOR.select(grid, np.ones((2, 2)), np.zeros((2, 2), dtype=bool), 1.0, None) == []
