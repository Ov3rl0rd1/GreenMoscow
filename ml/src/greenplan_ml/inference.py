from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime

from greenplan_ml.sample_builder import channel_pad_values, crop_offsets, pad_to_multiple

CELL_SIZE_KEY = "cell_size_m"
CHANNELS_KEY = "channels"
TARGET_CHANNELS_KEY = "target_channels"
SIZE_MULTIPLE_KEY = "size_multiple"
METADATA_SEPARATOR = ","
DEFAULT_TILE_CELLS = 512
DEFAULT_TILE_OVERLAP_CELLS = 64


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    cell_size_m: float
    channels: tuple[str, ...]
    target_channels: tuple[str, ...]
    size_multiple: int

    def as_properties(self) -> dict[str, str]:
        return {
            CELL_SIZE_KEY: str(self.cell_size_m),
            CHANNELS_KEY: METADATA_SEPARATOR.join(self.channels),
            TARGET_CHANNELS_KEY: METADATA_SEPARATOR.join(self.target_channels),
            SIZE_MULTIPLE_KEY: str(self.size_multiple),
        }

    @classmethod
    def from_properties(cls, properties: dict[str, str]) -> "ModelMetadata":
        return cls(
            cell_size_m=float(properties[CELL_SIZE_KEY]),
            channels=tuple(properties[CHANNELS_KEY].split(METADATA_SEPARATOR)),
            target_channels=tuple(properties[TARGET_CHANNELS_KEY].split(METADATA_SEPARATOR)),
            size_multiple=int(properties[SIZE_MULTIPLE_KEY]),
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
