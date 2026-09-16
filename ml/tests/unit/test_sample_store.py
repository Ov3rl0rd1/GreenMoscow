from pathlib import Path

import numpy as np

from greenplan.domain.norms import TREE
from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan_ml.feature_channels import CHANNEL_COUNT, CHANNEL_NAMES
from greenplan_ml.sample_builder import CropWindow
from greenplan_ml.sample_store import (
    ALLOWED_MASK_INDEX,
    CONDITIONAL_MASK_INDEX,
    GridMeta,
    ObjectMeta,
    PlantingMeta,
    ScaleMeta,
    masks_of,
    read_object,
    stored_objects,
    write_object,
)
from greenplan_ml.targets import TARGET_CHANNEL_COUNT, TARGET_CHANNELS

CROP_SIZE = 16


def meta_for(grid: RasterGrid) -> ObjectMeta:
    return ObjectMeta(
        object_id="demo",
        level="A",
        grid=GridMeta.of(grid),
        channels=CHANNEL_NAMES,
        target_channels=TARGET_CHANNELS,
        crop_size=CROP_SIZE,
        crops=(CropWindow(0, 0, 0.5), CropWindow(0, 16, 0.25)),
        tree_count=2,
        shrub_count=3,
        inside_boundary_share=0.9,
        scheme_id="pl_prefix",
        scales=ScaleMeta(5.0, 30.0, 12.0),
        plantings=(PlantingMeta(1.0, 2.0, TREE, "липа мелколистная"),),
    )


def write_demo(directory: Path) -> RasterGrid:
    grid = RasterGrid(10.0, 20.0, 0.5, CROP_SIZE, 32)
    features = np.random.default_rng(0).random((CHANNEL_COUNT, CROP_SIZE, 32)).astype(np.float32)
    targets = np.zeros((TARGET_CHANNEL_COUNT, CROP_SIZE, 32), dtype=np.float32)
    masks = np.ones((2, CROP_SIZE, 32), dtype=np.uint8)
    write_object(directory, features, targets, masks, meta_for(grid))
    return grid


def test_stored_object_returns_crops_of_the_declared_size(tmp_path: Path) -> None:
    write_demo(tmp_path / "demo")
    stored = read_object(tmp_path / "demo")
    features, targets = stored.crop(stored.meta.crops[1])
    assert features.shape == (CHANNEL_COUNT, CROP_SIZE, CROP_SIZE)
    assert targets.shape == (TARGET_CHANNEL_COUNT, CROP_SIZE, CROP_SIZE)
    assert features.dtype == np.float32


def test_metadata_survives_the_json_round_trip(tmp_path: Path) -> None:
    grid = write_demo(tmp_path / "demo")
    meta = read_object(tmp_path / "demo").meta
    assert meta.channels == CHANNEL_NAMES
    assert meta.grid.to_grid() == grid
    assert meta.plantings_of(TREE)[0].species_ru == "липа мелколистная"
    assert meta.scales.crown_saturation_m == 12.0


def test_objects_are_listed_and_filtered_by_identifier(tmp_path: Path) -> None:
    write_demo(tmp_path / "demo")
    assert [item.meta.object_id for item in stored_objects(tmp_path)] == ["demo"]
    assert stored_objects(tmp_path, ["other"]) == []


def test_masks_keep_allowed_and_conditional_layers() -> None:
    grid = RasterGrid(0.0, 0.0, 1.0, 2, 2)
    raster = SiteRaster(
        grid=grid,
        plantable=np.ones((2, 2), dtype=bool),
        allowed=np.array([[True, False], [True, True]]),
        conditional=np.array([[False, False], [True, False]]),
        clearance_m=np.zeros((2, 2), dtype=np.float32),
        reference_edge_distance_m=np.zeros((2, 2), dtype=np.float32),
    )
    masks = masks_of(raster)
    assert masks.shape == (2, 2, 2)
    assert masks[ALLOWED_MASK_INDEX].tolist() == [[1, 0], [1, 1]]
    assert masks[CONDITIONAL_MASK_INDEX].tolist() == [[0, 0], [1, 0]]
