from dataclasses import dataclass, field

from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE, SIDEWALK_EDGE
from greenplan.placement.composition_settings import CompositionSettings
from greenplan.placement.score_maps import RuleScoreWeights


def default_tree_score_weights() -> RuleScoreWeights:
    return RuleScoreWeights(
        clearance_weight=1.0,
        clearance_saturation_m=3.0,
        edge_weight=1.0,
        preferred_edge_distance_m=3.0,
        edge_tolerance_m=1.5,
        conditional_penalty=0.5,
    )


def default_shrub_score_weights() -> RuleScoreWeights:
    return RuleScoreWeights(
        clearance_weight=0.5,
        clearance_saturation_m=1.0,
        edge_weight=1.0,
        preferred_edge_distance_m=1.0,
        edge_tolerance_m=0.75,
        conditional_penalty=0.5,
    )


@dataclass(frozen=True, slots=True)
class PlacementSettings:
    cell_size_m: float = 0.5
    max_raster_cells: int = 24_000_000
    tree_crown_diameter_m: float = 5.0
    shrub_crown_diameter_m: float = 1.5
    allow_conditional: bool = True
    min_shrub_distance_to_planned_tree_m: float = 1.5
    tree_reference_edge_kind: str = CARRIAGEWAY_EDGE
    shrub_reference_edge_kind: str = SIDEWALK_EDGE
    tree_score: RuleScoreWeights = field(default_factory=default_tree_score_weights)
    shrub_score: RuleScoreWeights = field(default_factory=default_shrub_score_weights)
    spacing_rule_id: str = "ppm743_spacing_street"
    tree_spacing_key: str = "tree_single_row"
    shrub_spacing_key: str = "shrub_single_row_tall_gt_1_8m"
    density_rule_id: str = "tsn_max_density"
    density_context: str = "streets_embankments"
    range_bound: str = "upper"
    street_piece_gap_m: float = 100.0
    rejection_spacing_m: float = 3.0
    max_rejections_per_reason: int = 25
    max_rejections: int = 400
    rejection_seed: int = 0
    composition: CompositionSettings = field(default_factory=CompositionSettings)
    composition_edge_kinds: tuple[str, ...] = (CARRIAGEWAY_EDGE, SIDEWALK_EDGE)
