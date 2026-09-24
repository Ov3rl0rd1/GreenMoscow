from collections import defaultdict
from collections.abc import Callable
from math import floor

import numpy as np
from scipy.ndimage import label
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


class _Selection:
    def __init__(self, grid: RasterGrid, min_spacing_m: float, admit: AdmissionCheck) -> None:
        self._grid = grid
        self._min_spacing_m = min_spacing_m
        self._admit = admit
        self._taken = _SpatialHash(min_spacing_m)
        self.points: list[Point] = []

    def take(self, rows: np.ndarray, columns: np.ndarray, scores: np.ndarray, quota: int | None) -> int:
        taken = 0
        for index in np.argsort(-scores, kind="stable"):
            if quota is not None and taken >= quota:
                break
            x, y = self._grid.center_of(int(rows[index]), int(columns[index]))
            if self._taken.has_point_closer_than(x, y, self._min_spacing_m):
                continue
            point = Point(x, y)
            if self._admit(point):
                self._taken.add(x, y)
                self.points.append(point)
                taken += 1
        return taken


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
        selection = _Selection(grid, min_spacing_m, admit)
        selection.take(rows, columns, score[rows, columns], max_count)
        return selection.points

    def select_by_groups(
        self,
        grid: RasterGrid,
        score: np.ndarray,
        eligible: np.ndarray,
        min_spacing_m: float,
        max_count: int,
        admit: AdmissionCheck = admit_every_point,
    ) -> list[Point]:
        labels, count = label(eligible)
        rows, columns = np.nonzero(eligible)
        if count == 0 or max_count <= 0:
            return []
        scores = score[rows, columns]
        groups = labels[rows, columns]
        quotas = proportional_quotas(np.bincount(groups, weights=np.maximum(scores, 0.0))[1:], max_count)
        selection = _Selection(grid, min_spacing_m, admit)
        order = np.argsort(groups, kind="stable")
        bounds = np.searchsorted(groups[order], np.arange(1, count + 2))
        for group, quota in enumerate(quotas):
            if quota > 0:
                members = order[bounds[group] : bounds[group + 1]]
                selection.take(rows[members], columns[members], scores[members], quota)
        remaining = max_count - len(selection.points)
        if remaining > 0:
            selection.take(rows, columns, scores, remaining)
        return selection.points


def proportional_quotas(weights: np.ndarray, total: int) -> list[int]:
    mass = float(weights.sum())
    if mass <= 0:
        return [0] * len(weights)
    shares = weights / mass * total
    quotas = np.floor(shares).astype(int)
    leftover = total - int(quotas.sum())
    for index in np.argsort(-(shares - quotas), kind="stable")[:leftover]:
        quotas[index] += 1
    return quotas.tolist()
