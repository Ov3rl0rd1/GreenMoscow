from dataclasses import dataclass
from typing import Protocol

import numpy as np

from greenplan.domain.site import SiteModel
from greenplan.placement.raster import SiteRaster

RULES_GUIDANCE = "rules"
MODEL_GUIDANCE = "model"


@dataclass(frozen=True, slots=True, eq=False)
class PlacementGuidance:
    score: np.ndarray
    candidates: np.ndarray | None = None
    expected_count: int | None = None
    source: str = RULES_GUIDANCE


class ScoreMapProvider(Protocol):
    def score(self, raster: SiteRaster, site: SiteModel) -> np.ndarray: ...

    def guide(self, raster: SiteRaster, site: SiteModel) -> PlacementGuidance: ...


@dataclass(frozen=True, slots=True)
class RuleScoreWeights:
    clearance_weight: float
    clearance_saturation_m: float
    edge_weight: float
    preferred_edge_distance_m: float
    edge_tolerance_m: float
    conditional_penalty: float


class RuleScoreMap:
    def __init__(self, weights: RuleScoreWeights) -> None:
        self._weights = weights

    def guide(self, raster: SiteRaster, site: SiteModel) -> PlacementGuidance:
        return PlacementGuidance(self.score(raster, site))

    def score(self, raster: SiteRaster, site: SiteModel) -> np.ndarray:
        weights = self._weights
        combined = (
            weights.clearance_weight * self._clearance_term(raster)
            + weights.edge_weight * self._edge_term(raster)
            - weights.conditional_penalty * raster.conditional
        )
        return np.where(raster.allowed, combined, 0.0).astype(np.float32)

    def _clearance_term(self, raster: SiteRaster) -> np.ndarray:
        return np.clip(raster.clearance_m / self._weights.clearance_saturation_m, 0.0, 1.0)

    def _edge_term(self, raster: SiteRaster) -> np.ndarray:
        distance = raster.reference_edge_distance_m
        finite = np.isfinite(distance)
        offset = np.where(finite, distance - self._weights.preferred_edge_distance_m, 0.0)
        return np.where(finite, np.exp(-np.square(offset / self._weights.edge_tolerance_m)), 0.0)
