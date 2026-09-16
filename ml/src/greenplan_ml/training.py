import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from greenplan_ml.model import HeatmapUNet, UNetSettings
from greenplan_ml.onnx_export import save_checkpoint
from greenplan_ml.sample_store import StoredObject
from greenplan_ml.targets import CROWN_CHANNEL_INDEX, SHRUB_CHANNEL_INDEX, TREE_CHANNEL_INDEX

HISTORY_FILE = "history.json"
CHECKPOINT_FILE = "model.pt"
HEATMAP_CHANNELS = (TREE_CHANNEL_INDEX, SHRUB_CHANNEL_INDEX)


@dataclass(frozen=True, slots=True)
class TrainingProfile:
    name: str
    crop_size: int
    batch_size: int
    epochs: int
    learning_rate: float
    base_channels: int
    depth: int
    mixed_precision: bool
    num_workers: int
    weight_decay: float = 1e-4

    def unet_settings(self) -> UNetSettings:
        return UNetSettings(base_channels=self.base_channels, depth=self.depth)


PROFILES = {
    "smoke": TrainingProfile("smoke", 128, 2, 2, 3e-3, 16, 2, False, 0),
    "rtx3050": TrainingProfile("rtx3050", 256, 4, 40, 1e-3, 32, 3, True, 2),
    "gpu_large": TrainingProfile("gpu_large", 384, 16, 80, 1e-3, 48, 4, True, 6),
}


@dataclass(frozen=True, slots=True)
class EpochResult:
    epoch: int
    train_loss: float
    validation_loss: float


@dataclass(frozen=True, slots=True)
class TrainingHistory:
    profile: TrainingProfile
    epochs: tuple[EpochResult, ...]
    best_epoch: int
    checkpoint: Path

    def write(self, directory: Path) -> Path:
        path = directory / HISTORY_FILE
        payload = {
            "profile": asdict(self.profile),
            "epochs": [asdict(item) for item in self.epochs],
            "best_epoch": self.best_epoch,
            "checkpoint": self.checkpoint.name,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


class CropDataset(Dataset):
    def __init__(self, objects: Sequence[StoredObject], augment: bool = False, seed: int = 0) -> None:
        self._objects = list(objects)
        self._index = [
            (position, window)
            for position, item in enumerate(self._objects)
            for window in item.meta.crops
        ]
        self._augment = augment
        self._random = np.random.default_rng(seed)

    def __len__(self) -> int:
        return len(self._index)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        position, window = self._index[index]
        features, targets = self._objects[position].crop(window)
        if self._augment:
            features, targets = self._augmented(features, targets)
        return torch.from_numpy(features.copy()), torch.from_numpy(targets.copy())

    def _augmented(self, features: np.ndarray, targets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        turns = int(self._random.integers(0, 4))
        features = np.rot90(features, turns, axes=(1, 2))
        targets = np.rot90(targets, turns, axes=(1, 2))
        if self._random.random() < 0.5:
            features = features[:, :, ::-1]
            targets = targets[:, :, ::-1]
        return features, targets


class HeatmapLoss(nn.Module):
    def __init__(self, positive_weight: float = 8.0, crown_weight: float = 0.3, crown_floor: float = 0.2):
        super().__init__()
        self._positive_weight = positive_weight
        self._crown_weight = crown_weight
        self._crown_floor = crown_floor

    def forward(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        heat_prediction = prediction[:, HEATMAP_CHANNELS, :, :]
        heat_target = target[:, HEATMAP_CHANNELS, :, :]
        weights = 1.0 + self._positive_weight * heat_target
        heat_loss = (weights * (heat_prediction - heat_target) ** 2).mean()
        return heat_loss + self._crown_weight * self._crown_loss(prediction, target)

    def _crown_loss(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        mask = (target[:, HEATMAP_CHANNELS, :, :].amax(dim=1) > self._crown_floor).float()
        if mask.sum() == 0:
            return torch.zeros((), device=prediction.device)
        difference = (prediction[:, CROWN_CHANNEL_INDEX] - target[:, CROWN_CHANNEL_INDEX]).abs()
        return (difference * mask).sum() / mask.sum()


class Trainer:
    def __init__(self, model: HeatmapUNet, profile: TrainingProfile, device: torch.device) -> None:
        self._model = model.to(device)
        self._profile = profile
        self._device = device
        self._loss = HeatmapLoss()
        self._optimizer = torch.optim.AdamW(
            model.parameters(), lr=profile.learning_rate, weight_decay=profile.weight_decay
        )
        self._scaler = torch.amp.GradScaler(device.type, enabled=self._uses_amp())

    def fit(
        self,
        train_loader: DataLoader,
        validation_loader: DataLoader,
        output_directory: Path,
        cell_size_m: float,
    ) -> TrainingHistory:
        output_directory.mkdir(parents=True, exist_ok=True)
        checkpoint = output_directory / CHECKPOINT_FILE
        results: list[EpochResult] = []
        best_loss = float("inf")
        best_epoch = 0
        for epoch in range(1, self._profile.epochs + 1):
            train_loss = self._train_epoch(train_loader)
            validation_loss = self.evaluate(validation_loader)
            results.append(EpochResult(epoch, round(train_loss, 6), round(validation_loss, 6)))
            if validation_loss < best_loss:
                best_loss = validation_loss
                best_epoch = epoch
                save_checkpoint(checkpoint, self._model, cell_size_m)
        history = TrainingHistory(self._profile, tuple(results), best_epoch, checkpoint)
        history.write(output_directory)
        return history

    def evaluate(self, loader: DataLoader) -> float:
        self._model.eval()
        total = 0.0
        batches = 0
        with torch.no_grad():
            for features, targets in loader:
                prediction = self._model(features.to(self._device))
                total += float(self._loss(prediction, targets.to(self._device)))
                batches += 1
        return total / max(batches, 1)

    def _train_epoch(self, loader: DataLoader) -> float:
        self._model.train()
        total = 0.0
        batches = 0
        for features, targets in loader:
            self._optimizer.zero_grad(set_to_none=True)
            with torch.autocast(self._device.type, enabled=self._uses_amp()):
                prediction = self._model(features.to(self._device))
                loss = self._loss(prediction, targets.to(self._device))
            self._scaler.scale(loss).backward()
            self._scaler.step(self._optimizer)
            self._scaler.update()
            total += float(loss)
            batches += 1
        return total / max(batches, 1)

    def _uses_amp(self) -> bool:
        return self._profile.mixed_precision and self._device.type == "cuda"


def data_loader(dataset: CropDataset, profile: TrainingProfile, shuffle: bool) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=profile.batch_size,
        shuffle=shuffle,
        num_workers=profile.num_workers,
        drop_last=False,
    )


def split_objects(
    objects: Sequence[StoredObject], validation_ids: Sequence[str]
) -> tuple[list[StoredObject], list[StoredObject]]:
    wanted = set(validation_ids)
    validation = [item for item in objects if item.meta.object_id in wanted]
    train = [item for item in objects if item.meta.object_id not in wanted]
    if not validation and objects:
        return list(objects[:-1]), [objects[-1]]
    return train, validation


def select_device(requested: str | None = None) -> torch.device:
    if requested:
        return torch.device(requested)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def seed_everything(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
