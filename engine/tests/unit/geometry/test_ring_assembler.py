import pytest
from shapely.geometry import LineString

from greenplan.domain.site import (
    BOUNDARY_GAP_CLOSED,
    BOUNDARY_PIECES_JOINED,
    BOUNDARY_SELF_INTERSECTION_FIXED,
)
from greenplan.geometry.ring_assembler import RingAssembler

ASSEMBLER = RingAssembler(closure_tolerance_m=2.0, contact_tolerance_m=0.05, relative_closure_fraction=0.001)


def test_long_outline_with_proportionally_small_gap_is_closed() -> None:
    outline = LineString([(3.4, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)])
    assembled = ASSEMBLER.assemble([outline])
    assert sum(polygon.area for polygon in assembled.polygons) == pytest.approx(1_000_000.0)
    assert [repair.code for repair in assembled.repairs] == [BOUNDARY_GAP_CLOSED]


def test_short_fragment_is_not_closed_by_relative_rule() -> None:
    assert ASSEMBLER.assemble([LineString([(0, 0), (9, 0), (9.5, 0.5)])]).polygons == ()


def test_closed_ring_becomes_polygon_without_repairs() -> None:
    assembled = ASSEMBLER.assemble([LineString([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])])
    assert [polygon.area for polygon in assembled.polygons] == [pytest.approx(100.0)]
    assert assembled.repairs == ()


def test_small_gap_is_closed_and_reported() -> None:
    assembled = ASSEMBLER.assemble([LineString([(0.95, 0), (10, 0), (10, 10), (0, 10), (0, 0)])])
    assert sum(polygon.area for polygon in assembled.polygons) == pytest.approx(100.0)
    assert [(repair.code, round(repair.distance_m, 2)) for repair in assembled.repairs] == [
        (BOUNDARY_GAP_CLOSED, 0.95)
    ]


def test_open_pieces_are_joined_into_one_ring() -> None:
    lower = LineString([(0, 0), (10, 0), (10, 5)])
    upper = LineString([(10.06, 5), (10, 10), (0, 10), (0, 1.09)])
    assembled = ASSEMBLER.assemble([lower, upper])
    assert len(assembled.polygons) == 1
    assert assembled.polygons[0].area == pytest.approx(100.0, rel=0.02)
    assert sorted(repair.code for repair in assembled.repairs) == [
        BOUNDARY_PIECES_JOINED,
        BOUNDARY_PIECES_JOINED,
    ]


def test_gap_longer_than_tolerance_gives_no_polygon() -> None:
    assert ASSEMBLER.assemble([LineString([(5, 0), (10, 0), (10, 10), (0, 10), (0, 0)])]).polygons == ()


def test_self_intersecting_ring_is_split_into_valid_parts() -> None:
    bow_tie = LineString([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])
    assembled = ASSEMBLER.assemble([bow_tie])
    assert all(polygon.is_valid for polygon in assembled.polygons)
    assert sum(polygon.area for polygon in assembled.polygons) == pytest.approx(50.0)
    assert [repair.code for repair in assembled.repairs] == [BOUNDARY_SELF_INTERSECTION_FIXED]


def test_touching_pieces_are_joined_without_repairs() -> None:
    lower = LineString([(0, 0), (10, 0), (10, 10)])
    upper = LineString([(10, 10), (0, 10), (0, 0)])
    assembled = ASSEMBLER.assemble([lower, upper])
    assert sum(polygon.area for polygon in assembled.polygons) == pytest.approx(100.0)
    assert assembled.repairs == ()
