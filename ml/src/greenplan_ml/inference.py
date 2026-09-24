from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime

from greenplan_ml.sample_builder import channel_pad_values, crop_offsets, pad_to_multiple

CELL_SIZE_KEY = "cell_size_m"
CHANNELS_KEY = "channels"
TARGET_CHANNELS_KEY = "target_channels"
SIZE_MULTIPLE_KEY = "size_multiple"
CALIBRATION_PREFIX = "calibration"
THRESHOLD_FIELD = "threshold"
COUNT_SCALE_FIELD = "count_scale"
CALIBRATION_OBJECTS_KEY = "calibration.objects"
METADATA_SEPARATOR = ","
DEFAULT_TILE_CELLS = 512
DEFAULT_TILE_OVERLAP_CELLS = 64


@dataclass(frozen=True, slots=True)
class ChannelCalibration:
    threshold: float
    count_scale: float


@dataclass(frozen=True, slots=True)
class ModelCalibration:
    channels: dict[str, ChannelCalibration]
    objects: tuple[str, ...] = ()

    def for_channel(self, channel: str) -> ChannelCalibration | None:
        return self.channels.get(channel)

    def as_properties(self) -> dict[str, str]:
        properties = {CALIBRATION_OBJECTS_KEY: METADATA_SEPARATOR.join(self.objects)}
        for channel, values in self.channels.items():
            properties[calibration_key(channel, THRESHOLD_FIELD)] = f"{values.threshold:.6g}"
            properties[calibration_key(channel, COUNT_SCALE_FIELD)] = f"{values.count_scale:.6g}"
        return properties

    @classmethod
    def from_properties(
        cls, properties: dict[str, str], target_channels: tuple[str, ...]
    ) -> "ModelCalibration | None":
        channels = {
            channel: ChannelCalibration(
                threshold=float(properties[calibration_key(channel, THRESHOLD_FIELD)]),
                count_scale=float(properties[calibration_key(channel, COUNT_SCALE_FIELD)]),
            )
            for channel in target_channels
            if calibration_key(channel, THRESHOLD_FIELD) in properties
        }
        if not channels:
            return None
        objects = properties.get(CALIBRATION_OBJECTS_KEY, "")
        return cls(channels, tuple(item for item in objects.split(METADATA_SEPARATOR) if item))


def calibration_key(channel: str, field: str) -> str:
    return f"{CALIBRATION_PREFIX}.{channel}.{field}"


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    cell_size_m: float
    channels: tuple[str, ...]
    target_channels: tuple[str, ...]
    size_multiple: int
    calibration: ModelCalibration | None = None

    def as_properties(self) -> dict[str, str]:
        properties = {
            CELL_SIZE_KEY: str(self.cell_size_m),
            CHANNELS_KEY: METADATA_SEPARATOR.join(self.channels),
            TARGET_CHANNELS_KEY: METADATA_SEPARATOR.join(self.target_channels),
            SIZE_MULTIPLE_KEY: str(self.size_multiple),
        }
        if self.calibration is not None:
            properties.update(self.calibration.as_properties())
        return properties

    @classmethod
    def from_properties(cls, properties: dict[str, str]) -> "ModelMetadata":
        target_channels = tuple(properties[TARGET_CHANNELS_KEY].split(METADATA_SEPARATOR))
        return cls(
            cell_size_m=float(properties[CELL_SIZE_KEY]),
            channels=tuple(properties[CHANNELS_KEY].split(METADATA_SEPARATOR)),
            target_channels=target_channels,
            size_multiple=int(properties[SIZE_MULTIPLE_KEY]),
            calibration=ModelCalibration.from_properties(properties, target_channels),
        )


@dataclass(frozen=True, slots=True)
class TileSettings:
    tile_cells: int = DEFAULT_TILE_CELLS
    overlap_cells: int = DEFAULT_TILE_OVERLAP_CELLS


class OnnxHeatmapModel:
    def __init__(
        self,
        session: onnxruntime.InferenceSession,
        metadata: ModelMetadata,
        tiles: TileSettings | None = None,
    ) -> None:
        self._session = session
        self._metadata = metadata
        self._tiles = tiles or TileSettings()
        self._input_name = session.get_inputs()[0].name

    @classmethod
    def load(cls, path: Path, tiles: TileSettings | None = None) -> "OnnxHeatmapModel":
        session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        properties = session.get_modelmeta().custom_metadata_map
        return cls(session, ModelMetadata.from_properties(properties), tiles)

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    def channel_index(self, name: str) -> int:
        return self._metadata.target_channels.index(name)

    def predict(self, features: np.ndarray) -> np.ndarray:
        rows, columns = features.shape[1], features.shape[2]
        padded = pad_to_multiple(
            features.astype(np.float32),
            self._metadata.size_multiple,
            channel_pad_values(self._metadata.channels),
        )
        total = np.zeros((len(self._metadata.target_channels), *padded.shape[1:]), dtype=np.float32)
        counts = np.zeros(padded.shape[1:], dtype=np.float32)
        for row, column, window in self._windows(padded):
            prediction = self._run(window)
            total[:, row : row + window.shape[1], column : column + window.shape[2]] += prediction
            counts[row : row + window.shape[1], column : column + window.shape[2]] += 1.0
        return (total / np.maximum(counts, 1.0))[:, :rows, :columns]

    def _windows(self, padded: np.ndarray):
        tile = self._tile_cells()
        stride = max(tile - self._tiles.overlap_cells, self._metadata.size_multiple)
        for row in crop_offsets(padded.shape[1], tile, stride):
            for column in crop_offsets(padded.shape[2], tile, stride):
                yield row, column, padded[:, row : row + tile, column : column + tile]

    def _tile_cells(self) -> int:
        multiple = self._metadata.size_multiple
        return max(multiple, (self._tiles.tile_cells // multiple) * multiple)

    def _run(self, window: np.ndarray) -> np.ndarray:
        batch = window[None, ...].astype(np.float32)
        outputs = self._session.run(None, {self._input_name: batch})
        return np.asarray(outputs[0][0], dtype=np.float32)
