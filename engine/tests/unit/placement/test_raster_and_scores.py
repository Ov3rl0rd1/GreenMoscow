import numpy as np
import pytest
from shapely.geometry import Polygon

from greenplan.domain.site import SiteDiagnostics, SiteModel
from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan.placement.score_maps import RuleScoreMap, RuleScoreWeights

BARE_SITE = SiteModel(Polygon(), Polygon(), (), (), (), SiteDiagnostics())
WEIGHTS = RuleScoreWeights(
    clearance_weight=1.0,
    clearance_saturation_m=2.0,
    edge_weight=1.0,
    preferred_edge_distance_m=3.0,
    edge_tolerance_m=1.0,
    conditional_penalty=0.5,
)


def raster_row(clearance, edge_distance, allowed=None, conditional=None) -> SiteRaster:
    count = len(clearance)
    ones = np.ones((1, count), dtype=bool)
    return SiteRaster(
        grid=RasterGrid(0.0, 0.0, 1.0, 1, count),
        plantable=ones,
        allowed=ones if allowed is None else np.array([allowed]),
        conditional=np.zeros((1, count), dtype=bool) if conditional is None else np.array([conditional]),
        clearance_m=np.array([clearance], dtype=np.float32),
        reference_edge_distance_m=np.array([edge_distance], dtype=np.float32),
    )


def test_grid_covers_bounds_with_whole_cells() -> None:
    assert RasterGrid.covering((0.0, 0.0, 10.2, 4.0), 0.5).shape == (8, 21)


def test_cell_center_and_cell_index_are_consistent() -> None:
    grid = RasterGrid.covering((100.0, 200.0, 110.0, 210.0), 0.5)
    x, y = grid.center_of(3, 7)
    assert (x, y) == pytest.approx((103.75, 201.75))
    assert grid.cell_of(x, y) == (3, 7)


def test_cell_center_rows_run_along_y() -> None:
    xs, ys = RasterGrid.covering((0.0, 0.0, 2.0, 1.0), 0.5).cell_centers()
    assert xs.shape == (2, 4)
    assert ys[1, 0] == pytest.approx(0.75)
    assert xs[0, 3] == pytest.approx(1.75)


def test_score_grows_with_clearance_until_saturation() -> None:
    score = RuleScoreMap(WEIGHTS).score(raster_row([0.0, 1.0, 2.0, 4.0], [np.inf] * 4), BARE_SITE)[0]
    assert score[0] < score[1] < score[2]
    assert score[2] == pytest.approx(score[3])


def test_preferred_edge_distance_scores_highest() -> None:
    score = RuleScoreMap(WEIGHTS).score(raster_row([1.0] * 4, [1.0, 3.0, 5.0, np.inf]), BARE_SITE)[0]
    assert int(np.argmax(score)) == 1
    assert score[3] == pytest.approx(0.5)


def test_conditional_cells_are_penalized() -> None:
    score = RuleScoreMap(WEIGHTS).score(
        raster_row([1.0, 1.0], [3.0, 3.0], conditional=[False, True]), BARE_SITE
    )[0]
    assert score[1] == pytest.approx(score[0] - 0.5)


def test_disallowed_cells_score_zero() -> None:
    score = RuleScoreMap(WEIGHTS).score(
        raster_row([2.0, 2.0], [3.0, 3.0], allowed=[True, False]), BARE_SITE
    )[0]
    assert score[1] == 0.0
    assert score[0] > 0.0
