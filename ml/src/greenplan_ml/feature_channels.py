from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import shapely
from scipy.ndimage import distance_transform_edt
from shapely.geometry import MultiPolygon
from shapely.geometry.base import BaseGeometry

from greenplan.domain.obstacle_kinds import (
    BUILDING_WALL,
    CARRIAGEWAY_EDGE,
    COMMUNICATION_CABLE,
    GAS_PIPELINE,
    HEATING_NETWORK,
    OVERHEAD_LINE,
    POWER_CABLE,
    SEWER,
    SEWER_PRESSURE,
    SIDEWALK_EDGE,
    STORMWATER,
    WATER_SUPPLY,
)
from greenplan.domain.site import SiteModel
from greenplan.placement.planting_zones import PlantingZones
from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan.placement.site_rasterizer import SiteRasterizer

PLANTABLE_CHANNEL = "plantable"
CLEARANCE_CHANNEL = "plantable_clearance"
MASK_CHANNELS = (PLANTABLE_CHANNEL,)
OBSTACLE_DISTANCE_CHANNELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gas", (GAS_PIPELINE,)),
    ("water", (WATER_SUPPLY,)),
    ("sewer", (SEWER, SEWER_PRESSURE, STORMWATER)),
    ("heating", (HEATING_NETWORK,)),
    ("power_cable", (POWER_CABLE,)),
    ("communication_cable", (COMMUNICATION_CABLE,)),
    ("overhead_line", (OVERHEAD_LINE,)),
    ("carriageway_edge", (CARRIAGEWAY_EDGE,)),
    ("sidewalk_edge", (SIDEWALK_EDGE,)),
    ("building_wall", (BUILDING_WALL,)),
)
AREAL_GEOMETRY_TYPES = frozenset({"Polygon", "MultiPolygon"})
EXISTING_TREE_CHANNEL = "existing_tree"
STREET_AXIS_CHANNEL = "street_axis"
CHANNEL_NAMES = (
    PLANTABLE_CHANNEL,
    CLEARANCE_CHANNEL,
    *(name for name, _kinds in OBSTACLE_DISTANCE_CHANNELS),
    EXISTING_TREE_CHANNEL,
    STREET_AXIS_CHANNEL,
)
CHANNEL_COUNT = len(CHANNEL_NAMES)
PLANTABLE_CHANNEL_INDEX = CHANNEL_NAMES.index(PLANTABLE_CHANNEL)
CARRIAGEWAY_CHANNEL_INDEX = CHANNEL_NAMES.index("carriageway_edge")
EMPTY_ZONES = PlantingZones(MultiPolygon(), MultiPolygon())


@dataclass(frozen=True, slots=True)
class FeatureSettings:
    cell_size_m: float = 0.5
    max_distance_m: float = 30.0
    clearance_saturation_m: float = 5.0


@dataclass(frozen=True, slots=True, eq=False)
class FeatureStack:
    channels: np.ndarray
    grid: RasterGrid
    names: tuple[str, ...]

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.channels.shape


class FeatureStackBuilder:
    def __init__(self, settings: FeatureSettings | None = None) -> None:
        self._settings = settings or FeatureSettings()
        self._rasterizer = SiteRasterizer(self._settings.cell_size_m)

    def build(self, site: SiteModel) -> FeatureStack:
        return self.build_from_raster(site, self._rasterizer.rasterize(site, EMPTY_ZONES, CARRIAGEWAY_EDGE))

    def build_from_raster(self, site: SiteModel, raster: SiteRaster) -> FeatureStack:
        return self.build_on(site, raster.grid, raster.plantable)

    def build_on(self, site: SiteModel, grid: RasterGrid, plantable: np.ndarray) -> FeatureStack:
        channels = [plantable.astype(np.float32), self._clearance_channel(grid, plantable)]
        channels.extend(
            self._distance_channel(grid, _obstacle_geometries(site, kinds))
            for _name, kinds in OBSTACLE_DISTANCE_CHANNELS
        )
        channels.append(self._distance_channel(grid, [tree.position for tree in site.kept_trees()]))
        channels.append(self._distance_channel(grid, list(site.street_axes)))
        return FeatureStack(np.stack(channels).astype(np.float32), grid, CHANNEL_NAMES)

    def _clearance_channel(self, grid: RasterGrid, plantable: np.ndarray) -> np.ndarray:
        padded = np.pad(plantable, 1, constant_values=False)
        metres = distance_transform_edt(padded)[1:-1, 1:-1] * grid.cell_size_m
        return np.clip(metres / self._settings.clearance_saturation_m, 0.0, 1.0).astype(np.float32)

    def _distance_channel(self, grid: RasterGrid, geometries: Sequence[BaseGeometry]) -> np.ndarray:
        marked = mark_cells(grid, geometries, grid.cell_size_m)
        if not marked.any():
            return np.ones(grid.shape, dtype=np.float32)
        distances = distance_transform_edt(~marked) * grid.cell_size_m
        return np.clip(distances / self._settings.max_distance_m, 0.0, 1.0).astype(np.float32)


def mark_cells(grid: RasterGrid, geometries: Sequence[BaseGeometry], step_m: float) -> np.ndarray:
    marked = np.zeros(grid.shape, dtype=bool)
    rows, columns = cell_indices(grid, sampled_coordinates(geometries, step_m))
    if rows.size:
        marked[rows, columns] = True
    return marked


def sampled_coordinates(geometries: Sequence[BaseGeometry], step_m: float) -> np.ndarray:
    usable = [
        outline_of(geometry) for geometry in geometries if geometry is not None and not geometry.is_empty
    ]
    if not usable:
        return np.empty((0, 2), dtype=float)
    dense = shapely.segmentize(np.array(usable, dtype=object), step_m)
    coordinates = shapely.get_coordinates(dense)
    return coordinates[:, :2] if coordinates.size else np.empty((0, 2), dtype=float)


def outline_of(geometry: BaseGeometry) -> BaseGeometry:
    return geometry.boundary if geometry.geom_type in AREAL_GEOMETRY_TYPES else geometry


def cell_indices(grid: RasterGrid, coordinates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if not coordinates.size:
        return np.empty(0, dtype=int), np.empty(0, dtype=int)
    columns = np.floor((coordinates[:, 0] - grid.origin_x) / grid.cell_size_m).astype(int)
    rows = np.floor((coordinates[:, 1] - grid.origin_y) / grid.cell_size_m).astype(int)
    inside = (rows >= 0) & (rows < grid.rows) & (columns >= 0) & (columns < grid.columns)
    return rows[inside], columns[inside]


def _obstacle_geometries(site: SiteModel, kinds: Sequence[str]) -> list[BaseGeometry]:
    return [obstacle.geometry for kind in kinds for obstacle in site.obstacles_of(kind)]
