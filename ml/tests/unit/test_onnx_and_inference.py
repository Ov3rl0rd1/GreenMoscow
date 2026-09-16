from pathlib import Path

import numpy as np
import pytest
import torch

from greenplan_ml.feature_channels import CHANNEL_COUNT, CHANNEL_NAMES
from greenplan_ml.inference import ModelMetadata, OnnxHeatmapModel, TileSettings
from greenplan_ml.model import HeatmapUNet, UNetSettings
from greenplan_ml.onnx_export import Checkpoint, export_onnx, load_checkpoint, parity_error, save_checkpoint
from greenplan_ml.targets import TARGET_CHANNEL_COUNT, TARGET_CHANNELS

SETTINGS = UNetSettings(base_channels=4, depth=2)
CELL_SIZE_M = 0.5


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Checkpoint, Path]:
    directory = tmp_path_factory.mktemp("model")
    torch.manual_seed(0)
    checkpoint = save_checkpoint(directory / "model.pt", HeatmapUNet(SETTINGS), CELL_SIZE_M)
    loaded = load_checkpoint(checkpoint)
    return loaded, export_onnx(loaded, directory / "model.onnx", sample_size=32)


def test_metadata_survives_the_property_round_trip() -> None:
    metadata = ModelMetadata(0.5, CHANNEL_NAMES, TARGET_CHANNELS, 8)
    assert ModelMetadata.from_properties(metadata.as_properties()) == metadata


def test_checkpoint_keeps_the_architecture_and_the_cell_size(exported) -> None:
    checkpoint, _path = exported
    assert checkpoint.model.settings == SETTINGS
    assert checkpoint.cell_size_m == CELL_SIZE_M
    assert checkpoint.channels == CHANNEL_NAMES


def test_exported_model_carries_its_metadata(exported) -> None:
    _checkpoint, path = exported
    metadata = OnnxHeatmapModel.load(path).metadata
    assert metadata.cell_size_m == CELL_SIZE_M
    assert metadata.channels == CHANNEL_NAMES
    assert metadata.size_multiple == SETTINGS.size_multiple


def test_onnx_output_matches_pytorch(exported) -> None:
    checkpoint, path = exported
    sample = np.random.default_rng(1).random((CHANNEL_COUNT, 32, 32)).astype(np.float32)
    assert parity_error(checkpoint, path, sample) < 1e-4


def test_prediction_keeps_the_input_size_for_odd_shapes(exported) -> None:
    _checkpoint, path = exported
    features = np.zeros((CHANNEL_COUNT, 37, 53), dtype=np.float32)
    prediction = OnnxHeatmapModel.load(path).predict(features)
    assert prediction.shape == (TARGET_CHANNEL_COUNT, 37, 53)


def test_predictions_stay_within_the_probability_range(exported) -> None:
    _checkpoint, path = exported
    features = np.random.default_rng(2).random((CHANNEL_COUNT, 40, 40)).astype(np.float32)
    prediction = OnnxHeatmapModel.load(path).predict(features)
    assert prediction.min() >= 0.0
    assert prediction.max() <= 1.0


def test_tiling_covers_every_cell_of_a_large_input(exported) -> None:
    _checkpoint, path = exported
    model = OnnxHeatmapModel.load(path, TileSettings(tile_cells=32, overlap_cells=8))
    features = np.random.default_rng(3).random((CHANNEL_COUNT, 70, 90)).astype(np.float32)
    prediction = model.predict(features)
    assert prediction.shape == (TARGET_CHANNEL_COUNT, 70, 90)
    assert np.isfinite(prediction).all()


def test_tile_size_is_rounded_down_to_the_network_step(exported) -> None:
    _checkpoint, path = exported
    model = OnnxHeatmapModel.load(path, TileSettings(tile_cells=30, overlap_cells=4))
    features = np.zeros((CHANNEL_COUNT, 64, 64), dtype=np.float32)
    assert model.predict(features).shape == (TARGET_CHANNEL_COUNT, 64, 64)
