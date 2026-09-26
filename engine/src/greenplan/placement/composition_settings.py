from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompositionSettings:
    enabled: bool = True
    tree_row_offsets_m: tuple[float, ...] = (1.5, 2.5, 3.5, 5.0)
    tree_row_spacing_m: float = 6.0
    tree_row_min_size: int = 3
    tree_row_budget_share: float = 0.6
    tree_group_sizes: tuple[int, ...] = (5, 4, 3)
    tree_group_rotations: int = 6
    tree_group_gap_m: float = 9.0
    tree_group_min_filled_share: float = 0.75
    solitary_lawn_clearance_m: float = 5.0
    solitary_gap_m: float = 12.0
    hedge_offsets_m: tuple[float, ...] = (0.8, 1.2)
    hedge_min_size: int = 6
    hedge_budget_share: float = 0.5
    shrub_group_rings: tuple[int, ...] = (2, 1)
    shrub_group_small_sizes: tuple[int, ...] = (5, 3)
    shrub_group_gap_m: float = 3.0
    shrub_group_min_filled_share: float = 0.6
    seed_pool_factor: int = 40
    edge_simplify_m: float = 0.5
    edge_reach_m: float = 8.0
    line_confident_share: float = 0.5
    line_edge_weights: tuple[tuple[str, float], ...] = (("carriageway_edge", 1.5),)
