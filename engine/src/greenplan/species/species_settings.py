from dataclasses import dataclass

from greenplan.domain.norms import TREE


@dataclass(frozen=True, slots=True)
class SpeciesSettings:
    carriageway_context_distance_m: float = 6.0
    heating_context_distance_m: float = 4.0
    bus_stop_context_distance_m: float = 10.0
    overhead_line_context_distance_m: float = 3.0
    building_context_distance_m: float = 8.0
    allow_conditional_species: bool = False
    tree_grouping_distance_m: float = 8.0
    shrub_grouping_distance_m: float = 3.0
    prefer_bonus: float = 10.0
    limited_penalty: float = 5.0
    crown_class_bonus: float = 3.0
    reference_usage_weight: float = 1.0
    diversity_penalty: float = 8.0
    trait_bonus: float = 4.0
    noise_bonus: float = 3.0
    territory_limited_penalty: float = 2.0
    unlisted_penalty: float = 3.0
    additional_level_penalty: float = 1.0
    perspective_level_penalty: float = 2.0
    max_alternatives: int = 3
    tree_palette_size: int = 6
    shrub_palette_size: int = 6
    palette_bonus: float = 100.0

    def grouping_distance_m(self, target: str) -> float:
        return self.tree_grouping_distance_m if target == TREE else self.shrub_grouping_distance_m

    def palette_size(self, target: str) -> int:
        return self.tree_palette_size if target == TREE else self.shrub_palette_size
