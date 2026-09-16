from dataclasses import dataclass

import torch
from torch import nn

from greenplan_ml.feature_channels import CHANNEL_COUNT
from greenplan_ml.targets import TARGET_CHANNEL_COUNT


@dataclass(frozen=True, slots=True)
class UNetSettings:
    input_channels: int = CHANNEL_COUNT
    output_channels: int = TARGET_CHANNEL_COUNT
    base_channels: int = 32
    depth: int = 3
    dropout: float = 0.1

    @property
    def size_multiple(self) -> int:
        return 2**self.depth


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, dropout: float) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        return self.layers(batch)


class UpBlock(nn.Module):
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int, dropout: float) -> None:
        super().__init__()
        self.upsample = nn.ConvTranspose2d(in_channels, out_channels, 2, stride=2)
        self.block = ConvBlock(out_channels + skip_channels, out_channels, dropout)

    def forward(self, batch: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        return self.block(torch.cat([self.upsample(batch), skip], dim=1))


class HeatmapUNet(nn.Module):
    def __init__(self, settings: UNetSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or UNetSettings()
        widths = channel_widths(self.settings)
        self.stem = ConvBlock(self.settings.input_channels, widths[0], self.settings.dropout)
        self.pool = nn.MaxPool2d(2)
        self.encoders = nn.ModuleList(
            ConvBlock(widths[level], widths[level + 1], self.settings.dropout)
            for level in range(self.settings.depth)
        )
        self.decoders = nn.ModuleList(
            UpBlock(widths[level + 1], widths[level], widths[level], self.settings.dropout)
            for level in reversed(range(self.settings.depth))
        )
        self.head = nn.Conv2d(widths[0], self.settings.output_channels, 1)

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        features = self.stem(batch)
        skips = []
        for encoder in self.encoders:
            skips.append(features)
            features = encoder(self.pool(features))
        for decoder, skip in zip(self.decoders, reversed(skips), strict=True):
            features = decoder(features, skip)
        return torch.sigmoid(self.head(features))


def channel_widths(settings: UNetSettings) -> list[int]:
    return [settings.base_channels * 2**level for level in range(settings.depth + 1)]


def parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
