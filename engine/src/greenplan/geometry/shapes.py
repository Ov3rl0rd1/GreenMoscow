from collections.abc import Iterable

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

RING_CLOSURE_TOLERANCE_M = 0.05
MINIMUM_RING_POINTS = 4


def polygonal_parts(geometry: BaseGeometry | None) -> list[Polygon]:
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, (MultiPolygon, GeometryCollection)):
        return [part for member in geometry.geoms for part in polygonal_parts(member)]
    return []


def linear_parts(geometry: BaseGeometry | None) -> list[LineString]:
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, (MultiLineString, GeometryCollection)):
        return [part for member in geometry.geoms for part in linear_parts(member)]
    return []


def outline_lines(geometry: BaseGeometry | None) -> list[LineString]:
    rings = [
        LineString(ring.coords)
        for polygon in polygonal_parts(geometry)
        for ring in (polygon.exterior, *polygon.interiors)
    ]
    return [*linear_parts(geometry), *rings]


def polygon_from_closed_line(
    line: LineString, tolerance_m: float = RING_CLOSURE_TOLERANCE_M
) -> Polygon | None:
    coordinates = list(line.coords)
    if len(coordinates) < MINIMUM_RING_POINTS - 1:
        return None
    start, end = line.boundary.geoms if not line.is_ring and not line.boundary.is_empty else (None, None)
    if start is not None and start.distance(end) > tolerance_m:
        return None
    polygon = make_valid(Polygon(coordinates))
    parts = polygonal_parts(polygon)
    return max(parts, key=lambda part: part.area) if parts else None


def union_of_polygons(polygons: Iterable[Polygon]) -> Polygon | MultiPolygon:
    parts = [polygon for polygon in polygons if not polygon.is_empty]
    if not parts:
        return MultiPolygon()
    merged = unary_union(parts)
    polygons_only = polygonal_parts(merged)
    return polygons_only[0] if len(polygons_only) == 1 else MultiPolygon(polygons_only)
