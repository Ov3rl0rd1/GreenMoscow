import numpy as np

from greenplan_ml.feature_channels import CHANNEL_NAMES, CLEARANCE_CHANNEL, PLANTABLE_CHANNEL
from greenplan_ml.sample_builder import (
    EMPTY_MASK_VALUE,
    FAR_DISTANCE_VALUE,
    SampleSettings,
    channel_pad_values,
    crop_offsets,
    pad_to_multiple,
    pad_to_size,
    plan_crops,
)


def test_offsets_cover_the_tail_of_the_axis() -> None:
    assert crop_offsets(100, 40, 30) == [0, 30, 60]


def test_offsets_add_a_flush_window_when_stride_misses_the_end() -> None:
    assert crop_offsets(110, 40, 30) == [0, 30, 60, 70]


def test_shorter_axis_yields_a_single_offset() -> None:
    assert crop_offsets(30, 40, 30) == [0]


def test_crops_without_plantable_cells_are_dropped() -> None:
    plantable = np.zeros((64, 64), dtype=np.float32)
    plantable[:32, :32] = 1.0
    windows = plan_crops(plantable, SampleSettings(crop_size=32, stride=32))
    assert [(window.row, window.column) for window in windows] == [(0, 0)]


def test_crop_keeps_measured_plantable_fraction() -> None:
    plantable = np.zeros((32, 32), dtype=np.float32)
    plantable[:16, :] = 1.0
    window = plan_crops(plantable, SampleSettings(crop_size=32, stride=32))[0]
    assert window.plantable_fraction == 0.5


def test_masks_pad_with_zero_and_distances_pad_with_far_value() -> None:
    values = channel_pad_values(CHANNEL_NAMES)
    assert values[CHANNEL_NAMES.index(PLANTABLE_CHANNEL)] == EMPTY_MASK_VALUE
    assert values[CHANNEL_NAMES.index(CLEARANCE_CHANNEL)] == EMPTY_MASK_VALUE
    assert values[CHANNEL_NAMES.index("gas")] == FAR_DISTANCE_VALUE


def test_padding_to_size_fills_each_channel_with_its_own_value() -> None:
    stack = np.zeros((2, 3, 4), dtype=np.float32)
    padded = pad_to_size(stack, 6, np.array([0.0, 1.0], dtype=np.float32))
    assert padded.shape == (2, 6, 6)
    assert padded[0, 5, 5] == 0.0
    assert padded[1, 5, 5] == 1.0
    assert padded[1, 0, 0] == 0.0


def test_padding_to_multiple_rounds_up_both_axes() -> None:
    stack = np.zeros((2, 9, 17), dtype=np.float32)
    padded = pad_to_multiple(stack, 8, np.zeros(2, dtype=np.float32))
    assert padded.shape == (2, 16, 24)


def test_padding_to_multiple_keeps_an_exact_fit_untouched() -> None:
    stack = np.zeros((2, 16, 8), dtype=np.float32)
    assert pad_to_multiple(stack, 8, np.zeros(2, dtype=np.float32)) is stack
