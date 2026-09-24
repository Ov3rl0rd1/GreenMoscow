from collections.abc import Callable
from dataclasses import dataclass

from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.planting_limits import SpacingBounds
from greenplan.placement.score_maps import RuleScoreMap, ScoreMapProvider


@dataclass(frozen=True, slots=True)
class GuidanceMaps:
    tree: ScoreMapProvider
    shrub: ScoreMapProvider
    spacing: SpacingBounds = SpacingBounds()


GuidanceFactory = Callable[[PlacementSettings], GuidanceMaps]


def rule_guidance(settings: PlacementSettings) -> GuidanceMaps:
    return GuidanceMaps(RuleScoreMap(settings.tree_score), RuleScoreMap(settings.shrub_score))
