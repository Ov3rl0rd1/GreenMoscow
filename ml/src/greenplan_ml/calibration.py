from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter

from greenplan.domain.norms import SHRUB, TREE
from greenplan_ml.feature_channels import PLANTABLE_CHANNEL_INDEX, cell_indices
from greenplan_ml.inference import ChannelCalibration, ModelCalibration, OnnxHeatmapModel
from greenplan_ml.sample_store import StoredObject
from greenplan_ml.score_map import HEATMAP_CHANNEL_BY_TARGET, default_peak_sigma_m, peak_mass

PLANTABLE_LEVEL = 0.5


@dataclass(frozen=True, slots=True)
class CalibrationSettings:
    coverage: float = 0.8
    reach_m: float = 2.0
    min_threshold: float = 0.02


@dataclass(frozen=True, slots=True)
class ChannelEvidence:
    heat_at_plantings: np.ndarray
    plantings: int
    mass_in_plantings: float


class ModelCalibrator:
    def __init__(self, model: OnnxHeatmapModel, settings: CalibrationSettings | None = None) -> None:
        self._model = model
        self._settings = settings or CalibrationSettings()

    def calibrate(self, objects: Sequence[StoredObject]) -> ModelCalibration:
        evidence: dict[str, list[ChannelEvidence]] = {target: [] for target in (TREE, SHRUB)}
        for stored in objects:
            predictions = self._model.predict(np.asarray(stored.features, dtype=np.float32))
            plantable = np.asarray(stored.features[PLANTABLE_CHANNEL_INDEX]) > PLANTABLE_LEVEL
            for target in evidence:
                heat = predictions[self._model.channel_index(HEATMAP_CHANNEL_BY_TARGET[target])]
                evidence[target].append(self._evidence(stored, target, heat, plantable))
        channels = {
            HEATMAP_CHANNEL_BY_TARGET[target]: self._channel(target, items)
            for target, items in evidence.items()
            if sum(item.plantings for item in items)
        }
        return ModelCalibration(channels, tuple(stored.meta.object_id for stored in objects))

    def _evidence(
        self, stored: StoredObject, target: str, heat: np.ndarray, plantable: np.ndarray
    ) -> ChannelEvidence:
        grid = stored.meta.grid.to_grid()
        coordinates = np.array([[item.x, item.y] for item in stored.meta.plantings_of(target)], dtype=float)
        rows, columns = cell_indices(grid, coordinates.reshape(-1, 2))
        inside = plantable[rows, columns]
        reach_cells = max(1, int(round(self._settings.reach_m / grid.cell_size_m)))
        reachable = maximum_filter(heat, footprint=disk(reach_cells), mode="constant")
        sigma_cells = default_peak_sigma_m(target) / grid.cell_size_m
        return ChannelEvidence(
            heat_at_plantings=reachable[rows[inside], columns[inside]],
            plantings=int(inside.sum()),
            mass_in_plantings=float(np.clip(heat, 0.0, None)[plantable].sum()) / peak_mass(sigma_cells),
        )

    def _channel(self, target: str, items: Sequence[ChannelEvidence]) -> ChannelCalibration:
        values = np.concatenate([item.heat_at_plantings for item in items])
        threshold = float(np.quantile(values, 1.0 - self._settings.coverage)) if values.size else 0.0
        mass = sum(item.mass_in_plantings for item in items)
        plantings = sum(item.plantings for item in items)
        return ChannelCalibration(
            threshold=max(self._settings.min_threshold, threshold),
            count_scale=plantings / mass if mass > 0 else 1.0,
        )


def disk(radius_cells: int) -> np.ndarray:
    span = np.arange(-radius_cells, radius_cells + 1)
    return (span[:, None] ** 2 + span[None, :] ** 2) <= radius_cells**2
