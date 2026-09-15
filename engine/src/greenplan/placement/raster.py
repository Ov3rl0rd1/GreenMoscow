from dataclasses import dataclass
from math import ceil

import numpy as np


@dataclass(frozen=True, slots=True)
class RasterGrid:
    origin_x: float
    origin_y: float
    cell_size_m: float
    rows: int
    columns: int

    @classmethod
    def covering(cls, bounds: tuple[float, float, float, float], cell_size_m: float) -> "RasterGrid":
        min_x, min_y, max_x, max_y = bounds
        columns = max(1, ceil((max_x - min_x) / cell_size_m))
        rows = max(1, ceil((max_y - min_y) / cell_size_m))
        return cls(min_x, min_y, cell_size_m, rows, columns)

    @property
    def shape(self) -> tuple[int, int]:
        return self.rows, self.columns

    def cell_centers(self) -> tuple[np.ndarray, np.ndarray]:
        xs = self.origin_x + (np.arange(self.columns) + 0.5) * self.cell_size_m
        ys = self.origin_y + (np.arange(self.rows) + 0.5) * self.cell_size_m
        return np.meshgrid(xs, ys)

    def center_of(self, row: int, column: int) -> tuple[float, float]:
        return (
            self.origin_x + (column + 0.5) * self.cell_size_m,
            self.origin_y + (row + 0.5) * self.cell_size_m,
        )

    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        return int((y - self.origin_y) // self.cell_size_m), int((x - self.origin_x) // self.cell_size_m)


@dataclass(frozen=True, slots=True, eq=False)
class SiteRaster:
    grid: RasterGrid
    plantable: np.ndarray
    allowed: np.ndarray
    conditional: np.ndarray
    clearance_m: np.ndarray
    reference_edge_distance_m: np.ndarray
