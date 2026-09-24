from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExportSettings:
    layer_prefix: str = "AI"
    tree_layer_stem: str = "PL_TREES"
    shrub_layer_stem: str = "PL_BUSH"
    conditional_suffix: str = "COND"
    rejected_layer_stem: str = "REJECTED"
    zone_allowed_layer_stem: str = "ZONE_ALLOWED"
    zone_conditional_layer_stem: str = "ZONE_CONDITIONAL"
    zone_restricted_layer_stem: str = "ZONE_RESTRICTED"
    meta_layer_stem: str = "META"
    root_barrier_layer_stem: str = "ROOT_BARRIER"
    shrub_group_layer_stem: str = "BUSH_GROUPS"
    symbol_block_stem: str = "SYMBOL"
    tree_color: int = 3
    shrub_color: int = 82
    conditional_color: int = 30
    rejected_color: int = 1
    zone_allowed_color: int = 94
    zone_conditional_color: int = 40
    zone_restricted_color: int = 11
    meta_color: int = 7
    root_barrier_color: int = 6
    shrub_group_color: int = 82
    shrub_group_radius_m: float = 0.9
    shrub_group_min_size: int = 3
    shrub_group_simplify_m: float = 0.1
    shrub_group_hatch_pattern: str = "ANSI31"
    shrub_group_hatch_scale: float = 0.1
    xdata_application: str = "GREENPLAN"
    xdata_max_bytes: int = 250
    id_attribute_tag: str = "ID"
    label_height_m: float = 0.5
    rejection_marker_size_m: float = 0.6
    include_zones: bool = True
    include_rejections: bool = True
    include_shrub_groups: bool = True
    max_layer_name_length: int = 200
