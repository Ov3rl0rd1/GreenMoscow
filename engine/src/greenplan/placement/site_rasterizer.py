import numpy as np
import shapely
from scipy.ndimage import distance_transform_edt
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from greenplan.domain.site import Obstacle, SiteModel
from greenplan.placement.planting_zones import PlantingZones
from greenplan.placement.raster import RasterGrid, SiteRaster


class SiteRasterizer:
    def __init__(self, cell_size_m: float) -> None:
        self._cell_size_m = cell_size_m

    def rasterize(self, site: SiteModel, zones: PlantingZones, reference_edge_kind: str) -> SiteRaster:
        grid = RasterGrid.covering(_raster_bounds(site), self._cell_size_m)
        xs, ys = grid.cell_centers()
        plantable = _covered_cells(site.plantable_surface, xs, ys)
        allowed = plantable & ~_covered_cells(zones.prohibited, xs, ys)
        conditional = allowed & _covered_cells(zones.conditional, xs, ys)
        return SiteRaster(
            grid=grid,
            plantable=plantable,
            allowed=allowed,
            conditional=conditional,
            clearance_m=self._clearance_m(allowed),
            reference_edge_distance_m=_edge_distance_m(
                site.obstacles_of(reference_edge_kind), xs, ys, plantable
            ),
        )

    def _clearance_m(self, allowed: np.ndarray) -> np.ndarray:
        padded = np.pad(allowed, 1, constant_values=False)
        cells = distance_transform_edt(padded)[1:-1, 1:-1]
        return (cells * self._cell_size_m).astype(np.float32)


def _raster_bounds(site: SiteModel) -> tuple[float, float, float, float]:
    surface = site.boundary if site.plantable_surface.is_empty else site.plantable_surface
    return surface.bounds


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
