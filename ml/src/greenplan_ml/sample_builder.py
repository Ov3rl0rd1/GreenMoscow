from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from greenplan_ml.feature_channels import CHANNEL_NAMES, CLEARANCE_CHANNEL, MASK_CHANNELS

FAR_DISTANCE_VALUE = 1.0
EMPTY_MASK_VALUE = 0.0
PLANTABLE_CHANNEL_INDEX = CHANNEL_NAMES.index("plantable")
ZERO_PADDED_CHANNELS = (*MASK_CHANNELS, CLEARANCE_CHANNEL)


@dataclass(frozen=True, slots=True)
class SampleSettings:
    crop_size: int = 256
    stride: int = 192
    minimum_plantable_fraction: float = 0.02


@dataclass(frozen=True, slots=True)
class CropWindow:
    row: int
    column: int
    plantable_fraction: float


def crop_offsets(length: int, size: int, stride: int) -> list[int]:
    offsets = list(range(0, max(length - size, 0) + 1, stride))
    last = length - size
    if last > 0 and offsets[-1] != last:
        offsets.append(last)
    return offsets


def plan_crops(plantable: np.ndarray, settings: SampleSettings) -> list[CropWindow]:
    size = settings.crop_size
    windows = []
    for row in crop_offsets(plantable.shape[0], size, settings.stride):
        for column in crop_offsets(plantable.shape[1], size, settings.stride):
            fraction = float(plantable[row : row + size, column : column + size].mean())
            if fraction >= settings.minimum_plantable_fraction:
                windows.append(CropWindow(row, column, round(fraction, 4)))
    return windows


def channel_pad_values(names: Sequence[str]) -> np.ndarray:
    return np.array(
        [EMPTY_MASK_VALUE if name in ZERO_PADDED_CHANNELS else FAR_DISTANCE_VALUE for name in names],
        dtype=np.float32,
    )


def pad_to_size(stack: np.ndarray, size: int, pad_values: np.ndarray) -> np.ndarray:
    rows = max(size - stack.shape[1], 0)
    columns = max(size - stack.shape[2], 0)
    if rows == 0 and columns == 0:
        return stack
    padded = np.empty((stack.shape[0], stack.shape[1] + rows, stack.shape[2] + columns), dtype=stack.dtype)
    padded[:] = pad_values[:, None, None].astype(stack.dtype)
    padded[:, : stack.shape[1], : stack.shape[2]] = stack
    return padded


def pad_to_multiple(stack: np.ndarray, multiple: int, pad_values: np.ndarray) -> np.ndarray:
    rows = _rounded_up(stack.shape[1], multiple)
    columns = _rounded_up(stack.shape[2], multiple)
    if rows == stack.shape[1] and columns == stack.shape[2]:
        return stack
    padded = np.empty((stack.shape[0], rows, columns), dtype=stack.dtype)
    padded[:] = pad_values[:, None, None].astype(stack.dtype)
    padded[:, : stack.shape[1], : stack.shape[2]] = stack
    return padded


def _rounded_up(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple
