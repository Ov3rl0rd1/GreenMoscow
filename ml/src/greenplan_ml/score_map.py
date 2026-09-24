from dataclasses import dataclass
from math import pi
from pathlib import Path

import numpy as np

from greenplan.domain.errors import ConfigurationError
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.placement.guidance import GuidanceFactory, GuidanceMaps
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.planting_limits import LOWER_BOUND
from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan.placement.score_maps import MODEL_GUIDANCE, PlacementGuidance, RuleScoreMap, ScoreMapProvider
from greenplan_ml.feature_channels import FeatureSettings, FeatureStackBuilder
from greenplan_ml.inference import OnnxHeatmapModel, TileSettings
from greenplan_ml.targets import TargetSettings

TREE_HEATMAP_CHANNEL = "tree_heatmap"
SHRUB_HEATMAP_CHANNEL = "shrub_heatmap"
HEATMAP_CHANNEL_BY_TARGET = {TREE: TREE_HEATMAP_CHANNEL, SHRUB: SHRUB_HEATMAP_CHANNEL}
CELL_SIZE_TOLERANCE_M = 1e-6


@dataclass(frozen=True, slots=True)
class ModelScoreSettings:
    model_weight: float = 1.0
    rule_weight: float = 0.35
    heatmap_floor: float = 0.0
    candidate_threshold: float = 0.2
    count_scale: float = 1.0


class SitePredictions:
    def __init__(self, model: OnnxHeatmapModel, features: FeatureStackBuilder) -> None:
        self._model = model
        self._features = features
        self._key: tuple[int, RasterGrid] | None = None
        self._predictions: np.ndarray | None = None

    @property
    def model(self) -> OnnxHeatmapModel:
        return self._model

    def heatmap(self, raster: SiteRaster, site: SiteModel, channel: str) -> np.ndarray:
        key = (id(site), raster.grid)
        if self._key != key or self._predictions is None:
            stack = self._features.build_from_raster(site, raster)
            self._predictions = self._model.predict(stack.channels)
            self._key = key
        return self._predictions[self._model.channel_index(channel)]


class ModelScoreMap:
    def __init__(
        self,
        predictions: SitePredictions,
        rules: ScoreMapProvider,
        target: str,
        settings: ModelScoreSettings | None = None,
        peak_sigma_m: float | None = None,
    ) -> None:
        self._predictions = predictions
        self._rules = rules
        self._target = target
        self._channel = HEATMAP_CHANNEL_BY_TARGET[target]
        self._settings = settings or calibrated_settings(predictions.model, self._channel)
        self._peak_sigma_m = peak_sigma_m or default_peak_sigma_m(target)

    @classmethod
    def from_file(
        cls,
        path: Path,
        rules: ScoreMapProvider,
        target: str,
        settings: ModelScoreSettings | None = None,
        tiles: TileSettings | None = None,
    ) -> "ModelScoreMap":
        return cls(load_predictions(path, tiles), rules, target, settings)

    def score(self, raster: SiteRaster, site: SiteModel) -> np.ndarray:
        return self.guide(raster, site).score

    def guide(self, raster: SiteRaster, site: SiteModel) -> PlacementGuidance:
        self._require_matching_cell_size(raster)
        heatmap = self._predictions.heatmap(raster, site, self._channel)
        settings = self._settings
        combined = settings.model_weight * np.maximum(
            heatmap, settings.heatmap_floor
        ) + settings.rule_weight * self._rules.score(raster, site)
        return PlacementGuidance(
            score=np.where(raster.allowed, combined, 0.0).astype(np.float32),
            candidates=heatmap >= settings.candidate_threshold,
            expected_count=self._expected_count(heatmap, raster),
            source=MODEL_GUIDANCE,
        )

    def _expected_count(self, heatmap: np.ndarray, raster: SiteRaster) -> int:
        mass = float(np.clip(heatmap, 0.0, None)[raster.plantable].sum())
        sigma_cells = self._peak_sigma_m / raster.grid.cell_size_m
        return int(round(mass / peak_mass(sigma_cells) * self._settings.count_scale))

    def _require_matching_cell_size(self, raster: SiteRaster) -> None:
        expected = self._predictions.model.metadata.cell_size_m
        actual = raster.grid.cell_size_m
        if abs(expected - actual) > CELL_SIZE_TOLERANCE_M:
            raise ConfigurationError(
                f"модель обучена на клетке {expected} м, а размещение считает по {actual} м"
            )


def calibrated_settings(model: OnnxHeatmapModel, channel: str) -> ModelScoreSettings:
    calibration = model.metadata.calibration
    values = calibration.for_channel(channel) if calibration is not None else None
    if values is None:
        return ModelScoreSettings()
    return ModelScoreSettings(candidate_threshold=values.threshold, count_scale=values.count_scale)


def peak_mass(sigma_cells: float) -> float:
    return 2.0 * pi * sigma_cells**2


def default_peak_sigma_m(target: str) -> float:
    settings = TargetSettings()
    return settings.tree_sigma_m if target == TREE else settings.shrub_sigma_m


def load_predictions(path: Path, tiles: TileSettings | None = None) -> SitePredictions:
    model = OnnxHeatmapModel.load(path, tiles)
    features = FeatureStackBuilder(FeatureSettings(cell_size_m=model.metadata.cell_size_m))
    return SitePredictions(model, features)


def model_guidance(
    path: Path,
    tree_settings: ModelScoreSettings | None = None,
    shrub_settings: ModelScoreSettings | None = None,
) -> GuidanceFactory:
    predictions = load_predictions(path)

    def guidance(placement: PlacementSettings) -> GuidanceMaps:
        return GuidanceMaps(
            ModelScoreMap(predictions, RuleScoreMap(placement.tree_score), TREE, tree_settings),
            ModelScoreMap(predictions, RuleScoreMap(placement.shrub_score), SHRUB, shrub_settings),
            spacing_bound=LOWER_BOUND,
        )

    return guidance
