from collections.abc import Sequence

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from greenplan.geometry.shapes import polygonal_parts

BUFFER_SEGMENTS = 4


def shrub_group_areas(
    positions: Sequence[tuple[float, float]], radius_m: float, min_size: int, simplify_m: float
) -> list[Polygon]:
    if len(positions) < min_size:
        return []
    points = [Point(x, y) for x, y in positions]
    merged = unary_union([point.buffer(radius_m, quad_segs=BUFFER_SEGMENTS) for point in points])
    index = STRtree(points)
    return [
        polygon.simplify(simplify_m)
        for polygon in polygonal_parts(merged)
        if len(index.query(polygon, predicate="contains")) >= min_size
    ]
