from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import onnx
import torch

from greenplan_ml.feature_channels import CHANNEL_NAMES
from greenplan_ml.inference import ModelMetadata, OnnxHeatmapModel
from greenplan_ml.model import HeatmapUNet, UNetSettings
from greenplan_ml.targets import TARGET_CHANNELS

ONNX_OPSET = 17
INPUT_NAME = "features"
OUTPUT_NAME = "heatmaps"
MODEL_STATE_KEY = "model"
UNET_SETTINGS_KEY = "unet"
CELL_SIZE_KEY = "cell_size_m"
CHANNELS_KEY = "channels"
TARGET_CHANNELS_KEY = "target_channels"


@dataclass(frozen=True, slots=True)
class Checkpoint:
    model: HeatmapUNet
    cell_size_m: float
    channels: tuple[str, ...]
    target_channels: tuple[str, ...]

    def metadata(self) -> ModelMetadata:
        return ModelMetadata(
            cell_size_m=self.cell_size_m,
            channels=self.channels,
            target_channels=self.target_channels,
            size_multiple=self.model.settings.size_multiple,
        )


def save_checkpoint(path: Path, model: HeatmapUNet, cell_size_m: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            MODEL_STATE_KEY: model.state_dict(),
            UNET_SETTINGS_KEY: asdict(model.settings),
            CELL_SIZE_KEY: cell_size_m,
            CHANNELS_KEY: list(CHANNEL_NAMES),
            TARGET_CHANNELS_KEY: list(TARGET_CHANNELS),
        },
        path,
    )
    return path


def load_checkpoint(path: Path, device: str = "cpu") -> Checkpoint:
    content = torch.load(path, map_location=device, weights_only=True)
    settings = UNetSettings(**content[UNET_SETTINGS_KEY])
    model = HeatmapUNet(settings)
    model.load_state_dict(content[MODEL_STATE_KEY])
    model.eval()
    return Checkpoint(
        model=model,
        cell_size_m=float(content[CELL_SIZE_KEY]),
        channels=tuple(content[CHANNELS_KEY]),
        target_channels=tuple(content[TARGET_CHANNELS_KEY]),
    )


def export_onnx(checkpoint: Checkpoint, path: Path, sample_size: int = 128) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = checkpoint.model.settings
    size = max(sample_size, settings.size_multiple)
    sample = torch.zeros((1, settings.input_channels, size, size), dtype=torch.float32)
    axes = {0: "batch", 2: "rows", 3: "columns"}
    torch.onnx.export(
        checkpoint.model,
        sample,
        str(path),
        input_names=[INPUT_NAME],
        output_names=[OUTPUT_NAME],
        dynamic_axes={INPUT_NAME: axes, OUTPUT_NAME: axes},
        opset_version=ONNX_OPSET,
    )
    _write_metadata(path, checkpoint.metadata())
    return path


def parity_error(checkpoint: Checkpoint, onnx_path: Path, sample: np.ndarray) -> float:
    with torch.no_grad():
        expected = checkpoint.model(torch.from_numpy(sample[None, ...]).float()).numpy()[0]
    actual = OnnxHeatmapModel.load(onnx_path).predict(sample)
    return float(np.max(np.abs(expected - actual)))


def _write_metadata(path: Path, metadata: ModelMetadata) -> None:
    model = onnx.load(str(path))
    for key, value in metadata.as_properties().items():
        entry = model.metadata_props.add()
        entry.key = key
        entry.value = value
    onnx.save(model, str(path))
