import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan_ml.sample_builder import CropWindow

FEATURES_FILE = "features.npy"
TARGETS_FILE = "targets.npy"
MASKS_FILE = "masks.npy"
META_FILE = "meta.json"
STORAGE_DTYPE = np.float16
MASK_NAMES = ("allowed", "conditional")
ALLOWED_MASK_INDEX = 0
CONDITIONAL_MASK_INDEX = 1


@dataclass(frozen=True, slots=True)
class GridMeta:
    origin_x: float
    origin_y: float
    cell_size_m: float
    rows: int
    columns: int

    @classmethod
    def of(cls, grid: RasterGrid) -> "GridMeta":
        return cls(grid.origin_x, grid.origin_y, grid.cell_size_m, grid.rows, grid.columns)

    def to_grid(self) -> RasterGrid:
        return RasterGrid(self.origin_x, self.origin_y, self.cell_size_m, self.rows, self.columns)


@dataclass(frozen=True, slots=True)
class ScaleMeta:
    clearance_saturation_m: float
    max_distance_m: float
    crown_saturation_m: float


@dataclass(frozen=True, slots=True)
class PlantingMeta:
    x: float
    y: float
    target: str
    species_ru: str


@dataclass(frozen=True, slots=True)
class ObjectMeta:
    object_id: str
    level: str
    grid: GridMeta
    channels: tuple[str, ...]
    target_channels: tuple[str, ...]
    crop_size: int
    crops: tuple[CropWindow, ...]
    tree_count: int
    shrub_count: int
    inside_boundary_share: float
    scheme_id: str
    scales: ScaleMeta
    plantings: tuple[PlantingMeta, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def plantings_of(self, target: str) -> tuple[PlantingMeta, ...]:
        return tuple(planting for planting in self.plantings if planting.target == target)

    @classmethod
    def from_dict(cls, content: dict[str, Any]) -> "ObjectMeta":
        return cls(
            object_id=content["object_id"],
            level=content["level"],
            grid=GridMeta(**content["grid"]),
            channels=tuple(content["channels"]),
            target_channels=tuple(content["target_channels"]),
            crop_size=content["crop_size"],
            crops=tuple(CropWindow(**window) for window in content["crops"]),
            tree_count=content["tree_count"],
            shrub_count=content["shrub_count"],
            inside_boundary_share=content["inside_boundary_share"],
            scheme_id=content["scheme_id"],
            scales=ScaleMeta(**content["scales"]),
            plantings=tuple(PlantingMeta(**item) for item in content["plantings"]),
        )


@dataclass(frozen=True, slots=True, eq=False)
class StoredObject:
    meta: ObjectMeta
    features: np.ndarray
    targets: np.ndarray
    masks: np.ndarray

    def crop(self, window: CropWindow) -> tuple[np.ndarray, np.ndarray]:
        size = self.meta.crop_size
        rows = slice(window.row, window.row + size)
        columns = slice(window.column, window.column + size)
        return (
            np.asarray(self.features[:, rows, columns], dtype=np.float32),
            np.asarray(self.targets[:, rows, columns], dtype=np.float32),
        )


def masks_of(raster: SiteRaster) -> np.ndarray:
    return np.stack([raster.allowed, raster.conditional]).astype(np.uint8)


def write_object(
    directory: Path, features: np.ndarray, targets: np.ndarray, masks: np.ndarray, meta: ObjectMeta
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / FEATURES_FILE, features.astype(STORAGE_DTYPE))
    np.save(directory / TARGETS_FILE, targets.astype(STORAGE_DTYPE))
    np.save(directory / MASKS_FILE, masks.astype(np.uint8))
    (directory / META_FILE).write_text(
        json.dumps(meta.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return directory


def read_object(directory: Path) -> StoredObject:
    meta = ObjectMeta.from_dict(json.loads((directory / META_FILE).read_text(encoding="utf-8")))
    return StoredObject(
        meta=meta,
        features=np.load(directory / FEATURES_FILE, mmap_mode="r"),
        targets=np.load(directory / TARGETS_FILE, mmap_mode="r"),
        masks=np.load(directory / MASKS_FILE, mmap_mode="r"),
    )


def stored_objects(root: Path, object_ids: Sequence[str] | None = None) -> list[StoredObject]:
    directories = sorted(path.parent for path in root.glob(f"*/{META_FILE}"))
    objects = [read_object(directory) for directory in directories]
    if object_ids is None:
        return objects
    wanted = set(object_ids)
    return [item for item in objects if item.meta.object_id in wanted]
