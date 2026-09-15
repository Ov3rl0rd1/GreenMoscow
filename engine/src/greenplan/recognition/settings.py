from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecognitionSettings:
    annotation_match_distance_m: float = 3.0
    leader_text_distance_m: float = 1.0
    leader_max_length_m: float = 30.0
    arrow_max_length_m: float = 1.2
    arrow_tip_tolerance_m: float = 0.15
    leader_tip_match_distance_m: float = 0.5
    dashed_gap_bridge_m: float = 4.0
    dashed_alignment_cosine: float = 0.97
    symbol_cluster_gap_m: float = 0.25
    max_symbol_size_m: float = 3.0
    survey_coverage_radius_m: float = 25.0
    include_projected_networks: bool = True
    minimum_boundary_area_m2: float = 25.0
