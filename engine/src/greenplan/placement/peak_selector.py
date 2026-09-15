from collections import defaultdict
from collections.abc import Callable
from math import floor

import numpy as np
from shapely.geometry import Point

from greenplan.placement.raster import RasterGrid

AdmissionCheck = Callable[[Point], bool]


def admit_every_point(point: Point) -> bool:
    return True


class _SpatialHash:
    def __init__(self, bucket_size_m: float) -> None:
        self._bucket_size_m = bucket_size_m
        self._buckets: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)

    def add(self, x: float, y: float) -> None:
        self._buckets[self._key(x, y)].append((x, y))

    def has_point_closer_than(self, x: float, y: float, distance_m: float) -> bool:
        key_x, key_y = self._key(x, y)
        squared_limit = distance_m * distance_m
        for bucket_x in (key_x - 1, key_x, key_x + 1):
            for bucket_y in (key_y - 1, key_y, key_y + 1):
                for other_x, other_y in self._buckets.get((bucket_x, bucket_y), ()):
                    if (other_x - x) ** 2 + (other_y - y) ** 2 < squared_limit:
                        return True
        return False

    def _key(self, x: float, y: float) -> tuple[int, int]:
        return floor(x / self._bucket_size_m), floor(y / self._bucket_size_m)


class PeakSelector:
    def select(
        self,
        grid: RasterGrid,
        score: np.ndarray,
        eligible: np.ndarray,
        min_spacing_m: float,
        max_count: int | None,
        admit: AdmissionCheck = admit_every_point,
    ) -> list[Point]:
        rows, columns = np.nonzero(eligible)
        order = np.argsort(-score[rows, columns], kind="stable")
        taken = _SpatialHash(min_spacing_m)
        selected: list[Point] = []
        for index in order:
            if max_count is not None and len(selected) >= max_count:
                break
            x, y = grid.center_of(int(rows[index]), int(columns[index]))
            if taken.has_point_closer_than(x, y, min_spacing_m):
                continue
            point = Point(x, y)
            if admit(point):
                taken.add(x, y)
                selected.append(point)
        return selected
