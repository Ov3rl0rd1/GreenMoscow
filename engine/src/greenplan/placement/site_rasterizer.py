import numpy as np
import shapely
from scipy.ndimage import distance_transform_edt
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from greenplan.domain.site import Obstacle, SiteModel
from greenplan.placement.planting_zones import PlantingZones
from greenplan.placement.raster import RasterGrid, SiteRaster


class SiteRasterizer:
    def __init__(self, cell_size_m: float, max_cells: int | None = None) -> None:
        self._cell_size_m = cell_size_m
        self._max_cells = max_cells

    def rasterize(self, site: SiteModel, zones: PlantingZones, reference_edge_kind: str) -> SiteRaster:
        bounds = _raster_bounds(site, self._cell_size_m)
        grid = RasterGrid.covering(bounds, self._cell_size_m, self._max_cells)
        xs, ys = grid.cell_centers()
        plantable = _covered_cells(site.plantable_surface, xs, ys)
        allowed = plantable & ~_covered_cells(zones.prohibited, xs, ys)
        conditional = allowed & _covered_cells(zones.conditional, xs, ys)
        return SiteRaster(
            grid=grid,
            plantable=plantable,
            allowed=allowed,
            conditional=conditional,
            clearance_m=_clearance_m(allowed, grid.cell_size_m),
            reference_edge_distance_m=_edge_distance_m(
                site.obstacles_of(reference_edge_kind), xs, ys, plantable
            ),
        )


def _raster_bounds(site: SiteModel, cell_size_m: float) -> tuple[float, float, float, float]:
    if not site.plantable_surface.is_empty:
        return site.plantable_surface.bounds
    anchor = site.boundary.representative_point() if not site.boundary.is_empty else None
    x, y = (anchor.x, anchor.y) if anchor is not None else (0.0, 0.0)
    return x, y, x + cell_size_m, y + cell_size_m


def _clearance_m(allowed: np.ndarray, cell_size_m: float) -> np.ndarray:
    padded = np.pad(allowed, 1, constant_values=False)
    cells = distance_transform_edt(padded)[1:-1, 1:-1]
    return (cells * cell_size_m).astype(np.float32)


def _covered_cells(geometry: BaseGeometry, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    if geometry.is_empty:
        return np.zeros(xs.shape, dtype=bool)
    shapely.prepare(geometry)
    return shapely.contains_xy(geometry, xs, ys)


def _edge_distance_m(
    edges: tuple[Obstacle, ...], xs: np.ndarray, ys: np.ndarray, cells: np.ndarray
) -> np.ndarray:
    distances = np.full(xs.shape, np.inf, dtype=np.float32)
    if not edges or not cells.any():
        return distances
    tree = STRtree([edge.geometry for edge in edges])
    points = shapely.points(xs[cells], ys[cells])
    indices, nearest = tree.query_nearest(points, return_distance=True, all_matches=False)
    values = np.empty(points.shape[0], dtype=np.float32)
    values[indices[0]] = nearest
    distances[cells] = values
    return distances
