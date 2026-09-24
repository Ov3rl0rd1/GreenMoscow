from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from greenplan.domain.norms import SHRUB, TREE
from greenplan.placement.raster import RasterGrid
from greenplan_ml.calibration import CalibrationSettings, ModelCalibrator, disk
from greenplan_ml.feature_channels import CHANNEL_COUNT, CHANNEL_NAMES, PLANTABLE_CHANNEL_INDEX
from greenplan_ml.inference import ChannelCalibration, ModelCalibration, ModelMetadata, OnnxHeatmapModel
from greenplan_ml.model import HeatmapUNet, UNetSettings
from greenplan_ml.onnx_export import export_onnx, load_checkpoint, save_checkpoint, write_calibration
from greenplan_ml.sample_builder import CropWindow
from greenplan_ml.sample_store import GridMeta, ObjectMeta, PlantingMeta, ScaleMeta, read_object, write_object
from greenplan_ml.score_map import SHRUB_HEATMAP_CHANNEL, TREE_HEATMAP_CHANNEL, calibrated_settings
from greenplan_ml.targets import TARGET_CHANNEL_COUNT, TARGET_CHANNELS

SIZE = 32
CALIBRATION = ModelCalibration(
    {
        TREE_HEATMAP_CHANNEL: ChannelCalibration(0.15, 2.5),
        SHRUB_HEATMAP_CHANNEL: ChannelCalibration(0.05, 1.2),
    },
    ("kharkovskaya", "staryy_gay"),
)


@pytest.fixture(scope="module")
def model_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("calibration")
    torch.manual_seed(0)
    checkpoint = save_checkpoint(
        directory / "model.pt", HeatmapUNet(UNetSettings(base_channels=4, depth=2)), 0.5
    )
    return export_onnx(load_checkpoint(checkpoint), directory / "model.onnx", sample_size=32)


def stored(directory: Path):
    grid = RasterGrid(0.0, 0.0, 0.5, SIZE, SIZE)
    features = np.random.default_rng(0).random((CHANNEL_COUNT, SIZE, SIZE)).astype(np.float32)
    features[PLANTABLE_CHANNEL_INDEX] = 1.0
    meta = ObjectMeta(
        object_id="demo",
        level="A",
        grid=GridMeta.of(grid),
        channels=CHANNEL_NAMES,
        target_channels=TARGET_CHANNELS,
        crop_size=SIZE,
        crops=(CropWindow(0, 0, 1.0),),
        tree_count=2,
        shrub_count=1,
        inside_boundary_share=1.0,
        scheme_id="demo",
        scales=ScaleMeta(5.0, 30.0, 12.0),
        plantings=(
            PlantingMeta(4.0, 4.0, TREE, "липа"),
            PlantingMeta(10.0, 10.0, TREE, "клён"),
            PlantingMeta(6.0, 12.0, SHRUB, "сирень"),
        ),
    )
    targets = np.zeros((TARGET_CHANNEL_COUNT, SIZE, SIZE), dtype=np.float32)
    write_object(directory / "demo", features, targets, np.ones((2, SIZE, SIZE), dtype=np.uint8), meta)
    return read_object(directory / "demo")


def test_calibration_survives_the_metadata_round_trip() -> None:
    metadata = ModelMetadata(0.5, CHANNEL_NAMES, TARGET_CHANNELS, 8, CALIBRATION)
    assert ModelMetadata.from_properties(metadata.as_properties()) == metadata


def test_uncalibrated_metadata_has_no_calibration() -> None:
    metadata = ModelMetadata(0.5, CHANNEL_NAMES, TARGET_CHANNELS, 8)
    assert ModelMetadata.from_properties(metadata.as_properties()).calibration is None


def test_written_calibration_reaches_the_score_settings(model_path: Path, tmp_path: Path) -> None:
    calibrated = write_calibration(model_path, CALIBRATION, tmp_path / "calibrated.onnx")
    model = OnnxHeatmapModel.load(calibrated)
    assert model.metadata.cell_size_m == 0.5
    assert model.metadata.calibration == CALIBRATION
    settings = calibrated_settings(model, TREE_HEATMAP_CHANNEL)
    assert (settings.candidate_threshold, settings.count_scale) == (0.15, 2.5)


def test_calibrator_derives_threshold_and_scale_from_held_out_objects(
    model_path: Path, tmp_path: Path
) -> None:
    model = OnnxHeatmapModel.load(model_path)
    loose = ModelCalibrator(model, CalibrationSettings(coverage=1.0, min_threshold=0.0))
    strict = ModelCalibrator(model, CalibrationSettings(coverage=0.1, min_threshold=0.0))
    objects = [stored(tmp_path)]
    wide = loose.calibrate(objects).channels[TREE_HEATMAP_CHANNEL]
    narrow = strict.calibrate(objects).channels[TREE_HEATMAP_CHANNEL]
    assert wide.threshold <= narrow.threshold
    assert wide.count_scale > 0
    assert loose.calibrate(objects).objects == ("demo",)


def test_disk_footprint_is_round() -> None:
    footprint = disk(2)
    assert footprint.shape == (5, 5)
    assert footprint[2, 2] and not footprint[0, 0]


def test_replaced_calibration_keeps_other_channels() -> None:
    changed = replace(CALIBRATION, objects=("berzarina",))
    assert changed.for_channel(SHRUB_HEATMAP_CHANNEL) == ChannelCalibration(0.05, 1.2)
    assert changed.for_channel("crown_diameter") is None
