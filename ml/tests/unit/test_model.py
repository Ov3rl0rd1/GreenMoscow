import torch

from greenplan_ml.feature_channels import CHANNEL_COUNT
from greenplan_ml.model import HeatmapUNet, UNetSettings, channel_widths, parameter_count
from greenplan_ml.targets import TARGET_CHANNEL_COUNT

SETTINGS = UNetSettings(base_channels=4, depth=2)


def test_output_keeps_the_input_resolution() -> None:
    model = HeatmapUNet(SETTINGS)
    prediction = model(torch.zeros((2, CHANNEL_COUNT, 32, 48)))
    assert prediction.shape == (2, TARGET_CHANNEL_COUNT, 32, 48)


def test_predictions_are_probabilities() -> None:
    model = HeatmapUNet(SETTINGS)
    prediction = model(torch.randn((1, CHANNEL_COUNT, 16, 16)))
    assert float(prediction.min()) >= 0.0
    assert float(prediction.max()) <= 1.0


def test_size_multiple_follows_the_depth() -> None:
    assert UNetSettings(depth=3).size_multiple == 8
    assert UNetSettings(depth=4).size_multiple == 16


def test_channel_widths_double_at_every_level() -> None:
    assert channel_widths(UNetSettings(base_channels=8, depth=3)) == [8, 16, 32, 64]


def test_deeper_model_has_more_parameters() -> None:
    small = parameter_count(HeatmapUNet(UNetSettings(base_channels=4, depth=2)))
    large = parameter_count(HeatmapUNet(UNetSettings(base_channels=4, depth=3)))
    assert 0 < small < large
