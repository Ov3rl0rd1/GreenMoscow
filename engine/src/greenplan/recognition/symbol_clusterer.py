import math
from collections.abc import Sequence

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from greenplan.geometry.shapes import polygonal_parts


class SymbolClusterer:
    def __init__(self, cluster_gap_m: float, max_symbol_size_m: float) -> None:
        self._cluster_gap_m = cluster_gap_m
        self._max_symbol_size_m = max_symbol_size_m

    def symbol_positions(self, geometries: Sequence[BaseGeometry]) -> list[Point]:
        if not geometries:
            return []
        clusters = polygonal_parts(
            unary_union([geometry.buffer(self._cluster_gap_m) for geometry in geometries])
        )
        return [cluster.centroid for cluster in clusters if self._fits_symbol_size(cluster)]

    def _fits_symbol_size(self, cluster: BaseGeometry) -> bool:
        min_x, min_y, max_x, max_y = cluster.bounds
        diagonal = math.hypot(max_x - min_x, max_y - min_y) - 2 * self._cluster_gap_m
        return diagonal <= self._max_symbol_size_m
