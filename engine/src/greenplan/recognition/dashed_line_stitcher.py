from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Point
from shapely.strtree import STRtree

from greenplan.geometry.disjoint_set import DisjointSet
from greenplan.geometry.shapes import linear_parts

CONTACT_TOLERANCE_M = 1e-6


@dataclass(frozen=True, slots=True)
class _LineEnd:
    piece_index: int
    coordinate: np.ndarray
    outward_direction: np.ndarray


class DashedLineStitcher:
    def __init__(self, max_gap_m: float, min_alignment_cosine: float) -> None:
        self._max_gap_m = max_gap_m
        self._min_alignment_cosine = min_alignment_cosine

    def stitch(self, lines: Sequence[LineString]) -> list[LineString | MultiLineString]:
        pieces = _merged_pieces(lines)
        if not pieces:
            return []
        ends = _open_ends(pieces)
        links = self._mutual_best_links(ends)
        return _chains(pieces, ends, links)

    def _mutual_best_links(self, ends: Sequence[_LineEnd]) -> list[tuple[int, int]]:
        if not ends:
            return []
        tree = STRtree([Point(end.coordinate) for end in ends])
        partners = [self._best_partner(index, ends, tree) for index in range(len(ends))]
        return [
            (index, partner)
            for index, partner in enumerate(partners)
            if partner is not None and partner > index and partners[partner] == index
        ]

    def _best_partner(self, index: int, ends: Sequence[_LineEnd], tree: STRtree) -> int | None:
        end = ends[index]
        best_partner: int | None = None
        best_gap = float("inf")
        candidates = tree.query(Point(end.coordinate), predicate="dwithin", distance=self._max_gap_m)
        for candidate in candidates:
            other = ends[int(candidate)]
            if other.piece_index == end.piece_index:
                continue
            gap = float(np.hypot(*(other.coordinate - end.coordinate)))
            if gap < best_gap and self._continues(end, other, gap):
                best_partner, best_gap = int(candidate), gap
        return best_partner

    def _continues(self, end: _LineEnd, other: _LineEnd, gap: float) -> bool:
        if float(np.dot(end.outward_direction, other.outward_direction)) > -self._min_alignment_cosine:
            return False
        if gap <= CONTACT_TOLERANCE_M:
            return True
        bridge_direction = (other.coordinate - end.coordinate) / gap
        return float(np.dot(end.outward_direction, bridge_direction)) >= self._min_alignment_cosine


def _merged_pieces(lines: Sequence[LineString]) -> list[LineString]:
    valid = [line for line in lines if line.length > 0]
    if not valid:
        return []
    merged = shapely.line_merge(shapely.union_all(valid))
    return [piece for piece in linear_parts(merged) if piece.length > 0]


def _open_ends(pieces: Sequence[LineString]) -> list[_LineEnd]:
    ends: list[_LineEnd] = []
    for index, piece in enumerate(pieces):
        if piece.is_closed:
            continue
        coordinates = np.asarray(piece.coords)[:, :2]
        ends.append(_line_end(index, coordinates[0], coordinates[1]))
        ends.append(_line_end(index, coordinates[-1], coordinates[-2]))
    return ends


def _line_end(piece_index: int, end: np.ndarray, inner: np.ndarray) -> _LineEnd:
    vector = end - inner
    length = float(np.hypot(*vector))
    direction = vector / length if length > 0 else np.zeros(2)
    return _LineEnd(piece_index, end, direction)


def _chains(
    pieces: Sequence[LineString], ends: Sequence[_LineEnd], links: Sequence[tuple[int, int]]
) -> list[LineString | MultiLineString]:
    components = DisjointSet(len(pieces))
    bridges: dict[int, list[LineString]] = defaultdict(list)
    for first, second in links:
        first_end, second_end = ends[first], ends[second]
        components.union(first_end.piece_index, second_end.piece_index)
        if float(np.hypot(*(second_end.coordinate - first_end.coordinate))) > CONTACT_TOLERANCE_M:
            bridges[first_end.piece_index].append(LineString([first_end.coordinate, second_end.coordinate]))
    return [_chain_geometry(group, pieces, bridges) for group in components.groups()]


def _chain_geometry(
    group: Sequence[int], pieces: Sequence[LineString], bridges: dict[int, list[LineString]]
) -> LineString | MultiLineString:
    members = [pieces[index] for index in group] + [bridge for index in group for bridge in bridges[index]]
    if len(members) == 1:
        return members[0]
    return shapely.line_merge(MultiLineString(members))
