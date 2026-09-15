from collections.abc import Sequence
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from greenplan.domain.drawing import TextAnnotation


@dataclass(frozen=True, slots=True)
class LeaderDetection:
    leader_line_indices: frozenset[int] = frozenset()
    tip_by_annotation: dict[int, Point] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Leader:
    line_index: int
    tip: Point
    shelf: LineString
    wing_indices: tuple[int, ...]
    annotation_indices: tuple[int, ...]


class _ShortPieceIndex:
    def __init__(self, lines: Sequence[LineString], max_length_m: float) -> None:
        self._line_indices = [index for index, line in enumerate(lines) if line.length <= max_length_m]
        pieces = [lines[index] for index in self._line_indices]
        self._tree = STRtree(pieces) if pieces else None

    def touching(self, point: Point, tolerance_m: float) -> tuple[int, ...]:
        if self._tree is None:
            return ()
        found = self._tree.query(point, predicate="dwithin", distance=tolerance_m)
        return tuple(sorted(self._line_indices[int(index)] for index in found))


class LeaderLineDetector:
    def __init__(
        self,
        text_distance_m: float,
        max_leader_length_m: float,
        arrow_max_length_m: float,
        arrow_tip_tolerance_m: float,
    ) -> None:
        self._text_distance_m = text_distance_m
        self._max_leader_length_m = max_leader_length_m
        self._arrow_max_length_m = arrow_max_length_m
        self._arrow_tip_tolerance_m = arrow_tip_tolerance_m

    def detect(self, lines: Sequence[LineString], annotations: Sequence[TextAnnotation]) -> LeaderDetection:
        if not lines or not annotations:
            return LeaderDetection()
        wings = _ShortPieceIndex(lines, self._arrow_max_length_m)
        positions = [annotation.position for annotation in annotations]
        text_tree = STRtree(positions)
        leaders = [
            leader
            for index, line in enumerate(lines)
            if (leader := self._as_leader(index, line, wings, text_tree, positions)) is not None
        ]
        excluded = {leader.line_index for leader in leaders} | {
            wing for leader in leaders for wing in leader.wing_indices
        }
        return LeaderDetection(frozenset(excluded), _tips_by_nearest_shelf(leaders, positions))

    def _as_leader(
        self,
        index: int,
        line: LineString,
        wings: _ShortPieceIndex,
        text_tree: STRtree,
        positions: Sequence[Point],
    ) -> _Leader | None:
        if line.is_closed or not self._arrow_max_length_m < line.length <= self._max_leader_length_m:
            return None
        coordinates = list(line.coords)
        orientations = ((coordinates[-1], coordinates[:2]), (coordinates[0], coordinates[-2:]))
        for tip_coordinate, shelf_coordinates in orientations:
            tip, shelf = Point(tip_coordinate), LineString(shelf_coordinates)
            wing_indices = wings.touching(tip, self._arrow_tip_tolerance_m)
            if not wing_indices:
                continue
            annotation_indices = self._labels_on_shelf(shelf, tip, text_tree, positions)
            if annotation_indices:
                return _Leader(index, tip, shelf, wing_indices, annotation_indices)
        return None

    def _labels_on_shelf(
        self, shelf: LineString, tip: Point, text_tree: STRtree, positions: Sequence[Point]
    ) -> tuple[int, ...]:
        nearby = text_tree.query(shelf, predicate="dwithin", distance=self._text_distance_m)
        return tuple(
            int(index)
            for index in sorted(nearby)
            if positions[int(index)].distance(tip) > self._text_distance_m
        )


def _tips_by_nearest_shelf(leaders: Sequence[_Leader], positions: Sequence[Point]) -> dict[int, Point]:
    nearest: dict[int, tuple[float, Point]] = {}
    for leader in leaders:
        for annotation_index in leader.annotation_indices:
            distance = positions[annotation_index].distance(leader.shelf)
            if annotation_index not in nearest or distance < nearest[annotation_index][0]:
                nearest[annotation_index] = (distance, leader.tip)
    return {annotation_index: tip for annotation_index, (_distance, tip) in nearest.items()}
