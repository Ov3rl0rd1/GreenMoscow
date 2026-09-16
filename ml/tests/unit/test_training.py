from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from greenplan.domain.norms import TREE
from greenplan.placement.raster import RasterGrid
from greenplan_ml.feature_channels import CHANNEL_COUNT, CHANNEL_NAMES
from greenplan_ml.sample_builder import CropWindow
from greenplan_ml.sample_store import (
    GridMeta,
    ObjectMeta,
    PlantingMeta,
    ScaleMeta,
    read_object,
    write_object,
)
from greenplan_ml.targets import TARGET_CHANNEL_COUNT, TARGET_CHANNELS, TREE_CHANNEL_INDEX
from greenplan_ml.training import (
    PROFILES,
    CropDataset,
    HeatmapLoss,
    Trainer,
    data_loader,
    select_device,
    split_objects,
)

CROP_SIZE = 32
PROFILE = replace(PROFILES["smoke"], crop_size=CROP_SIZE, base_channels=4, depth=1, epochs=1, batch_size=2)


def store_object(directory: Path, object_id: str, crops: int = 2):
    grid = RasterGrid(0.0, 0.0, 0.5, CROP_SIZE, CROP_SIZE * crops)
    rng = np.random.default_rng(0)
    features = rng.random((CHANNEL_COUNT, grid.rows, grid.columns)).astype(np.float32)
    targets = np.zeros((TARGET_CHANNEL_COUNT, grid.rows, grid.columns), dtype=np.float32)
    targets[TREE_CHANNEL_INDEX, 8, 8] = 1.0
    masks = np.ones((2, grid.rows, grid.columns), dtype=np.uint8)
    meta = ObjectMeta(
        object_id=object_id,
        level="A",
        grid=GridMeta.of(grid),
        channels=CHANNEL_NAMES,
        target_channels=TARGET_CHANNELS,
        crop_size=CROP_SIZE,
        crops=tuple(CropWindow(0, index * CROP_SIZE, 1.0) for index in range(crops)),
        tree_count=1,
        shrub_count=0,
        inside_boundary_share=1.0,
        scheme_id="demo",
        scales=ScaleMeta(5.0, 30.0, 12.0),
        plantings=(PlantingMeta(4.0, 4.0, TREE, "липа мелколистная"),),
    )
    write_object(directory / object_id, features, targets, masks, meta)
    return read_object(directory / object_id)


def test_dataset_indexes_every_crop_of_every_object(tmp_path: Path) -> None:
    objects = [store_object(tmp_path, "first", 2), store_object(tmp_path, "second", 3)]
    dataset = CropDataset(objects)
    assert len(dataset) == 5
    features, targets = dataset[0]
    assert features.shape == (CHANNEL_COUNT, CROP_SIZE, CROP_SIZE)
    assert targets.shape == (TARGET_CHANNEL_COUNT, CROP_SIZE, CROP_SIZE)


def test_augmentation_keeps_shapes_and_value_range(tmp_path: Path) -> None:
    dataset = CropDataset([store_object(tmp_path, "first")], augment=True, seed=3)
    features, targets = dataset[0]
    assert features.shape == (CHANNEL_COUNT, CROP_SIZE, CROP_SIZE)
    assert float(targets.max()) <= 1.0


def test_named_objects_go_to_validation(tmp_path: Path) -> None:
    objects = [store_object(tmp_path, "first"), store_object(tmp_path, "second")]
    train, validation = split_objects(objects, ["first"])
    assert [item.meta.object_id for item in train] == ["second"]
    assert [item.meta.object_id for item in validation] == ["first"]


def test_last_object_is_held_out_when_nothing_is_named(tmp_path: Path) -> None:
    objects = [store_object(tmp_path, "first"), store_object(tmp_path, "second")]
    train, validation = split_objects(objects, [])
    assert [item.meta.object_id for item in train] == ["first"]
    assert [item.meta.object_id for item in validation] == ["second"]


def test_single_object_is_used_for_both_training_and_validation(tmp_path: Path) -> None:
    objects = [store_object(tmp_path, "only")]
    train, validation = split_objects(objects, [])
    assert [item.meta.object_id for item in train] == ["only"]
    assert [item.meta.object_id for item in validation] == ["only"]


def test_perfect_prediction_has_almost_no_loss() -> None:
    target = torch.zeros((1, TARGET_CHANNEL_COUNT, 8, 8))
    target[0, TREE_CHANNEL_INDEX, 4, 4] = 1.0
    assert float(HeatmapLoss()(target.clone(), target)) == pytest.approx(0.0, abs=1e-6)


def test_missing_a_peak_costs_more_than_a_false_positive() -> None:
    loss = HeatmapLoss()
    target = torch.zeros((1, TARGET_CHANNEL_COUNT, 8, 8))
    target[0, TREE_CHANNEL_INDEX, 4, 4] = 1.0
    missed = torch.zeros((1, TARGET_CHANNEL_COUNT, 8, 8))
    invented = target.clone()
    invented[0, TREE_CHANNEL_INDEX, 6, 6] = 1.0
    assert float(loss(missed, target)) > float(loss(invented, target))


def test_loss_falls_over_epochs_on_a_tiny_set(tmp_path: Path) -> None:
    from greenplan_ml.model import HeatmapUNet
    from greenplan_ml.training import seed_everything

    seed_everything(0)
    objects = [store_object(tmp_path / "data", "first", 3), store_object(tmp_path / "data", "second")]
    train, validation = split_objects(objects, ["second"])
    profile = replace(PROFILE, epochs=5)
    trainer = Trainer(HeatmapUNet(profile.unet_settings()), profile, select_device("cpu"))
    history = trainer.fit(
        data_loader(CropDataset(train), profile, True),
        data_loader(CropDataset(validation), profile, False),
        tmp_path / "run",
        0.5,
    )
    assert history.epochs[-1].train_loss < history.epochs[0].train_loss


def test_training_writes_weights_and_history(tmp_path: Path) -> None:
    from greenplan_ml.model import HeatmapUNet

    objects = [store_object(tmp_path / "data", "first"), store_object(tmp_path / "data", "second")]
    train, validation = split_objects(objects, ["second"])
    trainer = Trainer(HeatmapUNet(PROFILE.unet_settings()), PROFILE, select_device("cpu"))
    history = trainer.fit(
        data_loader(CropDataset(train), PROFILE, True),
        data_loader(CropDataset(validation), PROFILE, False),
        tmp_path / "run",
        0.5,
    )
    assert history.checkpoint.is_file()
    assert (tmp_path / "run" / "history.json").is_file()
    assert history.best_epoch == 1
    assert len(history.epochs) == 1
