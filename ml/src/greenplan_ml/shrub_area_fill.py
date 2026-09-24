from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from greenplan.geometry.shapes import linear_parts, polygon_from_closed_line, polygonal_parts


@dataclass(frozen=True, slots=True)
class AreaFillSettings:
    shrub_spacing_m: float = 0.9
    single_shrub_max_area_m2: float = 3.0
    minimum_area_m2: float = 0.2


class ShrubAreaFill:
    def __init__(self, settings: AreaFillSettings | None = None) -> None:
        self._settings = settings or AreaFillSettings()

    def positions(self, geometries: Sequence[BaseGeometry]) -> list[Point]:
        areas = unary_union([polygon for geometry in geometries for polygon in areal_parts(geometry)])
        points: list[Point] = []
        for area in polygonal_parts(areas):
            if area.area < self._settings.minimum_area_m2:
                continue
            if area.area <= self._settings.single_shrub_max_area_m2:
                points.append(area.representative_point())
            else:
                points.extend(self._filled(area))
        return points

    def _filled(self, area: Polygon) -> list[Point]:
        spacing = self._settings.shrub_spacing_m
        inside = hexagonal_points(area, spacing)
        return inside or along_axis(area, spacing) or [area.representative_point()]


def areal_parts(geometry: BaseGeometry) -> list[Polygon]:
    closed = [polygon_from_closed_line(line) for line in linear_parts(geometry) if line.is_ring]
    return [*polygonal_parts(geometry), *(polygon for polygon in closed if polygon is not None)]


def hexagonal_points(area: Polygon, spacing_m: float) -> list[Point]:
    min_x, min_y, max_x, max_y = area.bounds
    row_step = spacing_m * sqrt(3.0) / 2.0
    rows = np.arange(min_y + row_step / 2, max_y, row_step)
    xs, ys = [], []
    for index, y in enumerate(rows):
        offset = spacing_m / 2 if index % 2 else 0.0
        columns = np.arange(min_x + spacing_m / 2 + offset, max_x, spacing_m)
        xs.append(columns)
        ys.append(np.full(columns.shape, y))
    if not xs:
        return []
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    shapely.prepare(area)
    inside = shapely.contains_xy(area, x, y)
    return [Point(px, py) for px, py in zip(x[inside], y[inside], strict=True)]


def along_axis(area: Polygon, spacing_m: float) -> list[Point]:
    corners = list(area.minimum_rotated_rectangle.exterior.coords)[:4]
    if len(corners) < 4:
        return []
    first = LineString([corners[0], corners[1]])
    second = LineString([corners[1], corners[2]])
    long_side, short_side = (first, second) if first.length >= second.length else (second, first)
    offset = np.subtract(short_side.interpolate(0.5, normalized=True).coords[0], short_side.coords[0])
    axis = LineString([np.add(point, offset) for point in long_side.coords])
    reach = area.buffer(spacing_m / 2)
    steps = np.arange(spacing_m / 2, axis.length, spacing_m)
    return [point for point in (axis.interpolate(step) for step in steps) if reach.contains(point)]
