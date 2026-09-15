from collections.abc import Sequence
from dataclasses import dataclass

import shapely
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.strtree import STRtree
from shapely.validation import make_valid

from greenplan.domain.site import (
    BOUNDARY_GAP_CLOSED,
    BOUNDARY_PIECES_JOINED,
    BOUNDARY_SELF_INTERSECTION_FIXED,
    BoundaryRepair,
)
from greenplan.geometry.shapes import linear_parts, polygonal_parts

MINIMUM_RING_POINTS = 4


@dataclass(frozen=True, slots=True)
class AssembledRings:
    polygons: tuple[Polygon, ...]
    repairs: tuple[BoundaryRepair, ...]


@dataclass(frozen=True, slots=True)
class _LineEnd:
    piece_index: int
    point: Point


class RingAssembler:
    def __init__(
        self, closure_tolerance_m: float, contact_tolerance_m: float, relative_closure_fraction: float
    ) -> None:
        self._closure_tolerance_m = closure_tolerance_m
        self._contact_tolerance_m = contact_tolerance_m
        self._relative_closure_fraction = relative_closure_fraction

    def assemble(self, lines: Sequence[LineString]) -> AssembledRings:
        usable = [line for line in lines if len(line.coords) >= 2 and line.length > 0]
        closed = [line for line in usable if endpoint_gap(line) <= self._contact_tolerance_m]
        open_pieces = [line for line in usable if endpoint_gap(line) > self._contact_tolerance_m]
        bridges, join_repairs = self._joining_bridges(open_pieces)
        chain_rings, closure_repairs = self._closed_chains(open_pieces, bridges)
        polygons, validity_repairs = _polygons_of_rings(closed + chain_rings)
        return AssembledRings(tuple(polygons), tuple(join_repairs + closure_repairs + validity_repairs))

    def _joining_bridges(self, pieces: Sequence[LineString]) -> tuple[list[LineString], list[BoundaryRepair]]:
        ends = [
            _LineEnd(index, Point(piece.coords[position]))
            for index, piece in enumerate(pieces)
            for position in (0, -1)
        ]
        used: set[int] = set()
        bridges: list[LineString] = []
        repairs: list[BoundaryRepair] = []
        for distance, first, second in self._candidate_links(ends):
            if first in used or second in used:
                continue
            used.update((first, second))
            if distance > 0:
                bridges.append(LineString([ends[first].point, ends[second].point]))
            if distance > self._contact_tolerance_m:
                repairs.append(BoundaryRepair(BOUNDARY_PIECES_JOINED, distance))
        return bridges, repairs

    def _candidate_links(self, ends: Sequence[_LineEnd]) -> list[tuple[float, int, int]]:
        if not ends:
            return []
        tree = STRtree([end.point for end in ends])
        candidates: list[tuple[float, int, int]] = []
        for index, end in enumerate(ends):
            for other in tree.query(end.point, predicate="dwithin", distance=self._closure_tolerance_m):
                other_index = int(other)
                if other_index > index and ends[other_index].piece_index != end.piece_index:
                    candidates.append((end.point.distance(ends[other_index].point), index, other_index))
        return sorted(candidates)

    def _closed_chains(
        self, pieces: Sequence[LineString], bridges: Sequence[LineString]
    ) -> tuple[list[LineString], list[BoundaryRepair]]:
        if not pieces:
            return [], []
        rings: list[LineString] = []
        repairs: list[BoundaryRepair] = []
        for chain in linear_parts(shapely.line_merge(MultiLineString([*pieces, *bridges]))):
            gap = endpoint_gap(chain)
            if gap <= self._contact_tolerance_m:
                rings.append(chain)
            elif gap <= max(self._closure_tolerance_m, self._relative_closure_fraction * chain.length):
                rings.append(LineString([*chain.coords, chain.coords[0]]))
                repairs.append(BoundaryRepair(BOUNDARY_GAP_CLOSED, gap))
        return rings, repairs


def endpoint_gap(line: LineString) -> float:
    return Point(line.coords[0]).distance(Point(line.coords[-1]))


def _polygons_of_rings(rings: Sequence[LineString]) -> tuple[list[Polygon], list[BoundaryRepair]]:
    polygons: list[Polygon] = []
    repairs: list[BoundaryRepair] = []
    for ring in rings:
        if len(ring.coords) < MINIMUM_RING_POINTS:
            continue
        polygon = Polygon(ring.coords)
        if polygon.is_valid:
            polygons.append(polygon)
            continue
        polygons.extend(polygonal_parts(make_valid(polygon)))
        repairs.append(BoundaryRepair(BOUNDARY_SELF_INTERSECTION_FIXED, 0.0))
    return polygons, repairs
