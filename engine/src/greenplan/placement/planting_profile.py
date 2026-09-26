from dataclasses import dataclass

from greenplan.placement.score_maps import ScoreMapProvider


@dataclass(frozen=True, slots=True)
class PlantingProfile:
    target: str
    crown_diameter_m: float
    spacing_m: float
    max_count: int | None
    reference_edge_kind: str
    score_map: ScoreMapProvider
    allow_conditional: bool
    planned_plant_clearance_m: float
    composed: bool = False
    respects_density_cap: bool = True
    min_count_share: float = 0.0
