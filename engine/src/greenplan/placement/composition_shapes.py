from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from math import cos, hypot, pi, sin, sqrt

import numpy as np
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from greenplan.geometry.shapes import linear_parts, polygonal_parts

MASS_LOBE_DISTANCE = (0.75, 0.7)
MASS_LOBE_RADIUS = (0.65, 0.55)
MASS_LOBE_TURN = 2.4


@dataclass(frozen=True, slots=True)
class EdgeLine:
    line: LineString
    kind: str


@dataclass(frozen=True, slots=True)
class LinePoints:
    points: tuple[Point, ...]
    kind: str


def lawn_edges(lawn: BaseGeometry, simplify_m: float) -> list[EdgeLine]:
    rings = [ring for polygon in polygonal_parts(lawn) for ring in (polygon.exterior, *polygon.interiors)]
    return [EdgeLine(LineString(ring.coords).simplify(simplify_m), "") for ring in rings if ring.length > 0]


class EdgeClassifier:
    def __init__(self, lines_by_kind: dict[str, Sequence[LineString]], reach_m: float) -> None:
        self._reach_m = reach_m
        self._indexes = [(kind, STRtree(list(lines))) for kind, lines in lines_by_kind.items() if lines]

    def kind_near(self, point: Point) -> str:
        found = []
        for kind, index in self._indexes:
            nearest = index.query_nearest(point, max_distance=self._reach_m, return_distance=True)
            if len(nearest[1]):
                found.append((float(nearest[1].min()), kind))
        return min(found)[1] if found else ""


def offset_lines(
    edges: Sequence[EdgeLine], offsets_m: Sequence[float], spacing_m: float
) -> Iterator[LinePoints]:
    for edge in edges:
        for offset in offsets_m:
            for side in (1.0, -1.0):
                shifted = edge.line.offset_curve(side * offset)
                for part in linear_parts(shifted):
                    points = evenly_spaced(part, spacing_m)
                    if points:
                        yield LinePoints(points, edge.kind)


def evenly_spaced(line: LineString, spacing_m: float) -> tuple[Point, ...]:
    if line.length < spacing_m:
        return ()
    start = (line.length % spacing_m) / 2
    return tuple(line.interpolate(distance) for distance in np.arange(start, line.length, spacing_m))


def group_shape(center: Point, size: int, spacing_m: float, rotation: float) -> list[Point]:
    if size <= 1:
        return [center]
    radius = spacing_m / (2 * sin(pi / size))
    return [
        Point(
            center.x + radius * cos(rotation + 2 * pi * index / size),
            center.y + radius * sin(rotation + 2 * pi * index / size),
        )
        for index in range(size)
    ]


def hexagonal_size(rings: int) -> int:
    return 3 * rings * (rings + 1) + 1


def hexagonal_patch(center: Point, rings: int, spacing_m: float) -> list[Point]:
    points = []
    for q in range(-rings, rings + 1):
        for r in range(max(-rings, -q - rings), min(rings, -q + rings) + 1):
            x = center.x + spacing_m * (q + r / 2)
            y = center.y + spacing_m * r * sqrt(3) / 2
            points.append(Point(x, y))
    return points


def organic_mass(center: Point, radius_m: float, spacing_m: float, rotation: float) -> list[Point]:
    return [Point(center.x + dx, center.y + dy) for dx, dy in mass_offsets(radius_m, spacing_m, rotation)]


@lru_cache(maxsize=64)
def mass_offsets(radius_m: float, spacing_m: float, rotation: float) -> tuple[tuple[float, float], ...]:
    lobes = (
        (0.0, 0.0, radius_m),
        (
            MASS_LOBE_DISTANCE[0] * radius_m * cos(rotation),
            MASS_LOBE_DISTANCE[0] * radius_m * sin(rotation),
            MASS_LOBE_RADIUS[0] * radius_m,
        ),
        (
            MASS_LOBE_DISTANCE[1] * radius_m * cos(rotation + MASS_LOBE_TURN),
            MASS_LOBE_DISTANCE[1] * radius_m * sin(rotation + MASS_LOBE_TURN),
            MASS_LOBE_RADIUS[1] * radius_m,
        ),
    )
    reach = int(radius_m * 2 / spacing_m) + 1
    along = (cos(rotation), sin(rotation))
    across = (-sin(rotation), cos(rotation))
    offsets = []
    for row in range(-reach, reach + 1):
        for column in range(-reach, reach + 1):
            u = spacing_m * (column + (row % 2) / 2)
            v = spacing_m * row * sqrt(3) / 2
            x = u * along[0] + v * across[0]
            y = u * along[1] + v * across[1]
            if any(hypot(x - lx, y - ly) <= lr for lx, ly, lr in lobes):
                offsets.append((x, y))
    return tuple(offsets)


def band_points(points: Sequence[Point], rows: int, step_m: float, side: float) -> list[Point]:
    gap = step_m * sqrt(3) / 2
    result = list(points)
    for index, point in enumerate(points):
        tx, ty = tangent_at(points, index)
        nx, ny = -ty * side, tx * side
        for row in range(1, rows):
            shift = step_m / 2 if row % 2 else 0.0
            result.append(Point(point.x + nx * gap * row + tx * shift, point.y + ny * gap * row + ty * shift))
    return result


def tangent_at(points: Sequence[Point], index: int) -> tuple[float, float]:
    before = points[max(index - 1, 0)]
    after = points[min(index + 1, len(points) - 1)]
    dx, dy = after.x - before.x, after.y - before.y
    length = hypot(dx, dy) or 1.0
    return dx / length, dy / length


@dataclass(frozen=True, slots=True)
class CompanionLine:
    element_id: str
    line: LineString


class Companions:
    def __init__(self, lines: Sequence[CompanionLine], reach_m: float) -> None:
        self._lines = list(lines)
        self._reach_m = reach_m
        self._index = STRtree([item.line for item in self._lines]) if self._lines else None

    def near(self, point: Point) -> str:
        if self._index is None:
            return ""
        found = self._index.query_nearest(point, max_distance=self._reach_m)
        return self._lines[int(found[0])].element_id if len(found) else ""
