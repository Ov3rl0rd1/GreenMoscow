import pytest
from shapely.geometry import LineString, Point

from greenplan.geometry.disjoint_set import DisjointSet
from greenplan.recognition.dashed_line_stitcher import DashedLineStitcher

STITCHER = DashedLineStitcher(max_gap_m=4.0, min_alignment_cosine=0.97)


def dashes(count: int, dash_m: float = 1.0, gap_m: float = 0.5, y: float = 0.0) -> list[LineString]:
    step = dash_m + gap_m
    return [LineString([(index * step, y), (index * step + dash_m, y)]) for index in range(count)]


def test_collinear_dashes_become_one_chain_with_bridged_gaps() -> None:
    chains = STITCHER.stitch(dashes(10))
    assert len(chains) == 1
    assert chains[0].length == pytest.approx(10 * 1.0 + 9 * 0.5)
    assert chains[0].geom_type == "LineString"


def test_gap_longer_than_limit_is_not_bridged() -> None:
    chains = STITCHER.stitch([LineString([(0, 0), (10, 0)]), LineString([(15, 0), (25, 0)])])
    assert len(chains) == 2


def test_parallel_offset_line_is_not_attached() -> None:
    chains = STITCHER.stitch([LineString([(0, 0), (10, 0)]), LineString([(10.5, 1.0), (20, 1.0)])])
    assert len(chains) == 2


def test_straight_continuation_wins_over_perpendicular_branch() -> None:
    main_first = LineString([(0, 0), (10, 0)])
    main_second = LineString([(10.5, 0), (20, 0)])
    branch = LineString([(10.25, 0.3), (10.25, 10)])
    chains = sorted(STITCHER.stitch([main_first, main_second, branch]), key=lambda chain: chain.length)
    assert len(chains) == 2
    assert chains[1].length == pytest.approx(20.0)


def test_closed_ring_is_kept_as_separate_chain() -> None:
    well = Point(12, 0).buffer(0.5).exterior
    chains = STITCHER.stitch([LineString([(0, 0), (11, 0)]), well])
    assert len(chains) == 2


def test_touching_pieces_are_merged_without_bridges() -> None:
    chains = STITCHER.stitch([LineString([(0, 0), (5, 0)]), LineString([(5, 0), (5, 5)])])
    assert len(chains) == 1
    assert chains[0].length == pytest.approx(10.0)


def test_empty_input_gives_no_chains() -> None:
    assert STITCHER.stitch([]) == []


def test_disjoint_set_groups_connected_items() -> None:
    components = DisjointSet(5)
    components.union(0, 1)
    components.union(3, 4)
    components.union(1, 4)
    assert sorted(sorted(group) for group in components.groups()) == [[0, 1, 3, 4], [2]]
