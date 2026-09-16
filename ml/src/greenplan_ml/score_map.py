from dataclasses import dataclass
from pathlib import Path

import numpy as np

from greenplan.domain.errors import ConfigurationError
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.placement.raster import SiteRaster
from greenplan.placement.score_maps import RuleScoreMap, ScoreMapProvider
from greenplan_ml.feature_channels import FeatureSettings, FeatureStackBuilder
from greenplan_ml.inference import OnnxHeatmapModel, TileSettings

TREE_HEATMAP_CHANNEL = "tree_heatmap"
SHRUB_HEATMAP_CHANNEL = "shrub_heatmap"
HEATMAP_CHANNEL_BY_TARGET = {TREE: TREE_HEATMAP_CHANNEL, SHRUB: SHRUB_HEATMAP_CHANNEL}
CELL_SIZE_TOLERANCE_M = 1e-6


@dataclass(frozen=True, slots=True)
class ModelScoreSettings:
    model_weight: float = 1.0
    rule_weight: float = 0.35
    heatmap_floor: float = 0.0


class ModelScoreMap:
    def __init__(
        self,
        model: OnnxHeatmapModel,
        features: FeatureStackBuilder,
        rules: ScoreMapProvider,
        target: str,
        settings: ModelScoreSettings | None = None,
    ) -> None:
        self._model = model
        self._features = features
        self._rules = rules
        self._channel = HEATMAP_CHANNEL_BY_TARGET[target]
        self._settings = settings or ModelScoreSettings()

    @classmethod
    def from_file(
        cls,
        path: Path,
        rules: ScoreMapProvider,
        target: str,
        settings: ModelScoreSettings | None = None,
        tiles: TileSettings | None = None,
    ) -> "ModelScoreMap":
        model = OnnxHeatmapModel.load(path, tiles)
        features = FeatureStackBuilder(FeatureSettings(cell_size_m=model.metadata.cell_size_m))
        return cls(model, features, rules, target, settings)

    def score(self, raster: SiteRaster, site: SiteModel) -> np.ndarray:
        self._require_matching_cell_size(raster)
        stack = self._features.build_from_raster(site, raster)
        heatmap = self._model.predict(stack.channels)[self._model.channel_index(self._channel)]
        combined = self._settings.model_weight * np.maximum(
            heatmap, self._settings.heatmap_floor
        ) + self._settings.rule_weight * self._rules.score(raster, site)
        return np.where(raster.allowed, combined, 0.0).astype(np.float32)

    def _require_matching_cell_size(self, raster: SiteRaster) -> None:
        expected = self._model.metadata.cell_size_m
        actual = raster.grid.cell_size_m
        if abs(expected - actual) > CELL_SIZE_TOLERANCE_M:
            raise ConfigurationError(
                f"модель обучена на клетке {expected} м, а размещение считает по {actual} м"
            )


def tree_score_map(path: Path, rules: RuleScoreMap, settings: ModelScoreSettings | None = None):
    return ModelScoreMap.from_file(path, rules, TREE, settings)
