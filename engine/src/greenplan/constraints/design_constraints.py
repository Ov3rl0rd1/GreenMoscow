from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DesignConstraints:
    require_plantable_surface: bool = True
    min_tree_distance_to_existing_tree_m: float = 4.0
    min_shrub_distance_to_existing_tree_m: float = 1.0
    unknown_overhead_voltage_kv: float = 10.0
    clearance_tolerance_m: float = 1e-6
    obstacle_search_margin_m: float = 2.0
