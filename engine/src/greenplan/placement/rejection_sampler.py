from collections import Counter

import numpy as np

from greenplan.constraints.candidate_evaluator import CandidateEvaluator
from greenplan.domain.decisions import REJECTED, PlantCandidate, PlantingDecision, primary_rejection_reason
from greenplan.placement.peak_selector import PeakSelector
from greenplan.placement.planting_profile import PlantingProfile
from greenplan.placement.raster import SiteRaster


class RejectionSampler:
    def __init__(
        self, selector: PeakSelector, spacing_m: float, max_per_reason: int, max_total: int, seed: int
    ) -> None:
        self._selector = selector
        self._spacing_m = spacing_m
        self._max_per_reason = max_per_reason
        self._max_total = max_total
        self._seed = seed

    def sample(
        self, raster: SiteRaster, evaluator: CandidateEvaluator, profile: PlantingProfile
    ) -> tuple[PlantingDecision, ...]:
        forbidden = raster.plantable & ~raster.allowed
        shuffled_priority = np.random.default_rng(self._seed).random(raster.grid.shape)
        points = self._selector.select(raster.grid, shuffled_priority, forbidden, self._spacing_m, None)
        per_reason: Counter[str] = Counter()
        rejections: list[PlantingDecision] = []
        for point in points:
            if len(rejections) >= self._max_total:
                break
            decision = evaluator.evaluate(PlantCandidate("", point, profile.target, profile.crown_diameter_m))
            reason = primary_rejection_reason(decision)
            if decision.status != REJECTED or per_reason[reason] >= self._max_per_reason:
                continue
            per_reason[reason] += 1
            rejections.append(decision)
        return tuple(rejections)
