import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import shapely

from greenplan.domain.composition import ELEMENT_KINDS, HEDGE
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE, SIDEWALK_EDGE
from greenplan.domain.site import SiteModel
from greenplan.explain.explanation_model import PlantExplanation
from greenplan.explain.number_format import structure_value
from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

PRICES_FILE = Path("costs") / "unit_prices.yaml"
TREE_TIER = "деревья"
SHRUB_TIER = "кустарники"
LAWN_TIER = "газон и почвопокровные"
SQUARE_METRES_IN_HECTARE = 10000.0
TREE_SHELTER_REACH_M = 10.0
HEDGE_SHELTER_REACH_M = 3.0
SHADE_MARGIN_M = 1.0
SHRUB_COVER_RADIUS_M = 0.75
EDGE_SITE_MARGIN_M = 10.0


@dataclass(frozen=True, slots=True)
class PlanMetrics:
    species_count: int
    max_species_share: float
    tiers: tuple[str, ...]
    crown_projection_m2: float
    crown_share_of_plantable: float
    street_front_covered_m: float
    listed_species_share: float
    street_front_share: float | None = None
    sidewalk_shade_share: float | None = None
    open_lawn_share: float = 0.0
    elements: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class VolumeRow:
    name_ru: str
    plant_type: str
    count: int


@dataclass(frozen=True, slots=True)
class VolumeStatement:
    plants: tuple[VolumeRow, ...]
    trees: int
    shrubs: int
    lawn_area_m2: float
    root_barrier_length_m: float


@dataclass(frozen=True, slots=True)
class CostEstimate:
    total_rub: float
    per_hectare_rub: float
    reference_range_rub: tuple[float, float] | None
    within_reference_range: bool | None


class CostCatalog:
    def __init__(self, prices: dict[str, float], ranges: dict[str, tuple[float, float]]) -> None:
        self._prices = prices
        self._ranges = ranges

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "CostCatalog":
        path = knowledge_root / PRICES_FILE
        content = load_yaml_mapping(path)
        prices = {key: float(value) for key, value in require_key(content, "prices", path).items()}
        ranges = {
            key: (float(bounds[0]), float(bounds[1]))
            for key, bounds in (content.get("reference_range_per_hectare") or {}).items()
        }
        return cls(prices, ranges)

    def price(self, key: str) -> float:
        return self._prices.get(key, 0.0)

    def reference_range(self, category_id: str) -> tuple[float, float] | None:
        return self._ranges.get(category_id)

    def estimate(self, volumes: VolumeStatement, plantable_area_m2: float, category_id: str) -> CostEstimate:
        total = (
            volumes.trees * self.price("tree_each")
            + volumes.shrubs * self.price("shrub_each")
            + volumes.lawn_area_m2 * self.price("lawn_square_metre")
            + volumes.root_barrier_length_m * self.price("root_barrier_metre")
        )
        hectares = plantable_area_m2 / SQUARE_METRES_IN_HECTARE
        per_hectare = total / hectares if hectares > 0 else 0.0
        bounds = self.reference_range(category_id)
        within = None if bounds is None or per_hectare == 0 else bounds[0] <= per_hectare <= bounds[1]
        return CostEstimate(
            total_rub=structure_value(total),
            per_hectare_rub=structure_value(per_hectare),
            reference_range_rub=bounds,
            within_reference_range=within,
        )


def plan_metrics(
    site: SiteModel, plants: Sequence[PlantExplanation], listed_keys: Sequence[str]
) -> PlanMetrics:
    names = [plant.species.name_ru for plant in plants if plant.species is not None]
    counts = Counter(names)
    listed = {key for key in listed_keys}
    with_species = [plant for plant in plants if plant.species is not None]
    return PlanMetrics(
        species_count=len(counts),
        max_species_share=structure_value(max(counts.values()) / len(names) if names else 0.0),
        tiers=_tiers(site, plants),
        crown_projection_m2=structure_value(_crown_projection_m2(plants)),
        crown_share_of_plantable=structure_value(
            _crown_projection_m2(plants) / site.plantable_surface.area
            if site.plantable_surface.area > 0
            else 0.0
        ),
        street_front_covered_m=structure_value(_street_front_covered_m(site, plants)),
        listed_species_share=structure_value(
            sum(1 for plant in with_species if plant.species.key in listed) / len(with_species)
            if with_species
            else 0.0
        ),
        street_front_share=optional_value(street_front_share(site, plants)),
        sidewalk_shade_share=optional_value(sidewalk_shade_share(site, plants)),
        open_lawn_share=structure_value(open_lawn_share(site, plants)),
        elements=element_counts(plants),
    )


def optional_value(value: float | None) -> float | None:
    return None if value is None else structure_value(value)


def street_front_share(site: SiteModel, plants: Sequence[PlantExplanation]) -> float | None:
    trees = [plant for plant in plants if plant.plant_type == TREE]
    hedges = [plant for plant in plants if plant.element is not None and plant.element.kind == HEDGE]
    shelter = shapely.union_all(
        [
            *(shapely.Point(plant.x, plant.y).buffer(TREE_SHELTER_REACH_M) for plant in trees),
            *(shapely.Point(plant.x, plant.y).buffer(HEDGE_SHELTER_REACH_M) for plant in hedges),
        ]
    )
    return covered_share(site_edges(site, CARRIAGEWAY_EDGE), shelter)


def sidewalk_shade_share(site: SiteModel, plants: Sequence[PlantExplanation]) -> float | None:
    crowns = shapely.union_all(
        [
            shapely.Point(plant.x, plant.y).buffer(plant.crown_diameter_m / 2 + SHADE_MARGIN_M)
            for plant in plants
            if plant.plant_type == TREE
        ]
    )
    return covered_share(site_edges(site, SIDEWALK_EDGE), crowns)


def open_lawn_share(site: SiteModel, plants: Sequence[PlantExplanation]) -> float:
    lawn = site.plantable_surface
    if lawn.area <= 0:
        return 0.0
    cover = shapely.union_all(
        [
            shapely.Point(plant.x, plant.y).buffer(
                plant.crown_diameter_m / 2 if plant.plant_type == TREE else SHRUB_COVER_RADIUS_M
            )
            for plant in plants
        ]
    )
    return max(0.0, 1.0 - lawn.intersection(cover).area / lawn.area)


def site_edges(site: SiteModel, kind: str) -> list[shapely.Geometry]:
    reach = site.boundary.buffer(EDGE_SITE_MARGIN_M)
    clipped = [obstacle.geometry.intersection(reach) for obstacle in site.obstacles_of(kind)]
    return [edge for edge in clipped if not edge.is_empty]


def covered_share(edges: Sequence[shapely.Geometry], cover: shapely.Geometry) -> float | None:
    total = sum(edge.length for edge in edges)
    if total <= 0:
        return None
    if cover.is_empty:
        return 0.0
    return sum(edge.intersection(cover).length for edge in edges) / total


def element_counts(plants: Sequence[PlantExplanation]) -> tuple[tuple[str, int], ...]:
    kinds = Counter(
        {
            plant.element.element_id: plant.element.kind for plant in plants if plant.element is not None
        }.values()
    )
    return tuple((kind, kinds[kind]) for kind in ELEMENT_KINDS if kinds[kind])


def volume_statement(
    plants: Sequence[PlantExplanation], lawn_area_m2: float, root_barrier_length_m: float
) -> VolumeStatement:
    counts = Counter(
        (plant.species.name_ru, plant.plant_type) for plant in plants if plant.species is not None
    )
    rows = tuple(VolumeRow(name, plant_type, count) for (name, plant_type), count in counts.most_common())
    return VolumeStatement(
        plants=rows,
        trees=sum(1 for plant in plants if plant.plant_type == TREE),
        shrubs=sum(1 for plant in plants if plant.plant_type == SHRUB),
        lawn_area_m2=structure_value(lawn_area_m2),
        root_barrier_length_m=structure_value(root_barrier_length_m),
    )


def _tiers(site: SiteModel, plants: Sequence[PlantExplanation]) -> tuple[str, ...]:
    found = []
    if any(plant.plant_type == TREE for plant in plants):
        found.append(TREE_TIER)
    if any(plant.plant_type == SHRUB for plant in plants):
        found.append(SHRUB_TIER)
    if site.plantable_surface.area > 0:
        found.append(LAWN_TIER)
    return tuple(found)


def _crown_projection_m2(plants: Sequence[PlantExplanation]) -> float:
    return sum(math.pi * (plant.crown_diameter_m / 2) ** 2 for plant in plants)


def _street_front_covered_m(
    site: SiteModel, plants: Sequence[PlantExplanation], reach_m: float = 10.0
) -> float:
    edges = [obstacle.geometry for obstacle in site.obstacles_of(CARRIAGEWAY_EDGE)]
    trees = [plant for plant in plants if plant.plant_type == TREE]
    if not edges or not trees:
        return 0.0
    canopy = shapely.union_all(shapely.points([(plant.x, plant.y) for plant in trees])).buffer(reach_m)
    return sum(edge.intersection(canopy).length for edge in edges)
