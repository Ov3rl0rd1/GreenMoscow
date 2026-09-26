from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from math import cos, pi, sin, sqrt

import numpy as np
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from greenplan.geometry.shapes import linear_parts, polygonal_parts


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


def hexagonal_patch(center: Point, rings: int, spacing_m: float) -> list[Point]:
    points = []
    for q in range(-rings, rings + 1):
        for r in range(max(-rings, -q - rings), min(rings, -q + rings) + 1):
            x = center.x + spacing_m * (q + r / 2)
            y = center.y + spacing_m * r * sqrt(3) / 2
            points.append(Point(x, y))
    return points
