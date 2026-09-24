from dataclasses import dataclass
from math import ceil, sqrt

import numpy as np


@dataclass(frozen=True, slots=True)
class RasterGrid:
    origin_x: float
    origin_y: float
    cell_size_m: float
    rows: int
    columns: int

    @classmethod
    def covering(
        cls, bounds: tuple[float, float, float, float], cell_size_m: float, max_cells: int | None = None
    ) -> "RasterGrid":
        min_x, min_y, max_x, max_y = bounds
        cell = affordable_cell_size(max_x - min_x, max_y - min_y, cell_size_m, max_cells)
        columns = max(1, ceil((max_x - min_x) / cell))
        rows = max(1, ceil((max_y - min_y) / cell))
        return cls(min_x, min_y, cell, rows, columns)

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


def affordable_cell_size(width: float, height: float, cell_size_m: float, max_cells: int | None) -> float:
    if max_cells is None or width * height <= max_cells * cell_size_m**2:
        return cell_size_m
    return sqrt(width * height / max_cells)


@dataclass(frozen=True, slots=True, eq=False)
class SiteRaster:
    grid: RasterGrid
    plantable: np.ndarray
    allowed: np.ndarray
    conditional: np.ndarray
    clearance_m: np.ndarray
    reference_edge_distance_m: np.ndarray
