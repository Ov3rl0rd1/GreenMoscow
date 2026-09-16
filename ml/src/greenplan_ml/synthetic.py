import random
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon, box

from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.obstacle_kinds import (
    CARRIAGEWAY_EDGE,
    COMMUNICATION_CABLE,
    GAS_PIPELINE,
    POWER_CABLE,
    SEWER,
    SIDEWALK_EDGE,
    WATER_SUPPLY,
)
from greenplan.domain.site import KEEP_TREE_STATUS, ExistingTree, Obstacle, SiteDiagnostics, SiteModel
from greenplan_ml.reference_conventions import SHRUB_TYPE, TREE_TYPE
from greenplan_ml.reference_extractor import ReferencePlanting

SYNTHETIC_SOURCE = "synthetic"
SYNTHETIC_SCHEME = "synthetic"
TREE_SPECIES = "липа мелколистная"
SHRUB_SPECIES = "кизильник блестящий"
NETWORK_EVIDENCE = ("source:synthetic",)


@dataclass(frozen=True, slots=True)
class StreetSettings:
    length_m: float = 160.0
    lawn_width_m: float = 24.0
    carriageway_width_m: float = 12.0
    sidewalk_width_m: float = 3.0
    tree_spacing_m: float = 8.0
    tree_offset_m: float = 12.0
    shrub_spacing_m: float = 2.0
    shrub_offset_m: float = 5.0
    tree_gap_probability: float = 0.15
    seed: int = 0


@dataclass(frozen=True, slots=True)
class SyntheticStreet:
    site: SiteModel
    plantings: tuple[ReferencePlanting, ...]


class SyntheticStreetGenerator:
    def __init__(self, settings: StreetSettings | None = None) -> None:
        self._settings = settings or StreetSettings()

    def generate(self, seed: int | None = None) -> SyntheticStreet:
        settings = self._settings
        source = random.Random(settings.seed if seed is None else seed)
        length = settings.length_m
        lawn_top = settings.lawn_width_m
        lawn = box(0.0, 0.0, length, lawn_top)
        boundary = box(
            -settings.sidewalk_width_m, -settings.carriageway_width_m, length + 5.0, lawn_top + 5.0
        )
        obstacles = (
            *self._edges(length, lawn_top),
            *self._networks(length, lawn_top, source),
        )
        trees = self._kept_trees(length, lawn_top, source)
        axis_y = -settings.carriageway_width_m / 2
        site = SiteModel(
            boundary=boundary,
            plantable_surface=lawn,
            obstacles=obstacles,
            existing_trees=trees,
            street_axes=(LineString([(0.0, axis_y), (length, axis_y)]),),
            diagnostics=SiteDiagnostics(boundary_source=SYNTHETIC_SOURCE, lawn_source=SYNTHETIC_SOURCE),
        )
        return SyntheticStreet(site, self._plantings(site, lawn, source))

    def _edges(self, length: float, lawn_top: float) -> tuple[Obstacle, ...]:
        carriageway = LineString([(0.0, 0.0), (length, 0.0)])
        sidewalk = LineString([(0.0, lawn_top), (length, lawn_top)])
        return (
            _obstacle(CARRIAGEWAY_EDGE, carriageway),
            _obstacle(SIDEWALK_EDGE, sidewalk),
        )

    def _networks(self, length: float, lawn_top: float, source: random.Random) -> tuple[Obstacle, ...]:
        plan = (
            (GAS_PIPELINE, 0.08, 0.15),
            (WATER_SUPPLY, 0.92, 0.25),
            (SEWER, -0.35, 0.3),
            (POWER_CABLE, 1.2, 0.05),
            (COMMUNICATION_CABLE, 1.3, 0.05),
        )
        networks = []
        for kind, share, radius in plan:
            offset = lawn_top * share + source.uniform(-0.6, 0.6)
            middle = offset + source.uniform(-1.0, 1.0)
            line = LineString([(0.0, offset), (length * 0.5, middle), (length, offset)])
            networks.append(_obstacle(kind, line, radius))
        return tuple(networks)

    def _kept_trees(self, length: float, lawn_top: float, source: random.Random) -> tuple[ExistingTree, ...]:
        count = source.randint(1, 4)
        return tuple(
            ExistingTree(
                Point(source.uniform(5.0, length - 5.0), source.uniform(1.0, lawn_top - 1.0)),
                KEEP_TREE_STATUS,
                "synthetic_trees",
                SYNTHETIC_SOURCE,
            )
            for _ in range(count)
        )

    def _plantings(
        self, site: SiteModel, lawn: Polygon, source: random.Random
    ) -> tuple[ReferencePlanting, ...]:
        settings = self._settings
        plantings = [
            *self._row(site, lawn, settings.tree_offset_m, settings.tree_spacing_m, TREE, source),
            *self._row(site, lawn, settings.shrub_offset_m, settings.shrub_spacing_m, SHRUB, source),
        ]
        return tuple(plantings)

    def _row(
        self,
        site: SiteModel,
        lawn: Polygon,
        offset_m: float,
        spacing_m: float,
        target: str,
        source: random.Random,
    ) -> list[ReferencePlanting]:
        minimum_x, _minimum_y, maximum_x, _maximum_y = lawn.bounds
        clearance = 2.0 if target == TREE else 1.0
        row: list[ReferencePlanting] = []
        position_x = minimum_x + spacing_m
        while position_x < maximum_x - spacing_m:
            point = Point(position_x, offset_m + source.uniform(-0.3, 0.3))
            keeps_place = source.random() > self._settings.tree_gap_probability
            if keeps_place and self._is_free(site, point, clearance):
                row.append(_planting(point, target))
            position_x += spacing_m
        return row

    def _is_free(self, site: SiteModel, point: Point, clearance_m: float) -> bool:
        networks = [obstacle for obstacle in site.obstacles if obstacle.outer_radius_m is not None]
        if any(point.distance(obstacle.geometry) < clearance_m for obstacle in networks):
            return False
        return all(point.distance(tree.position) > 4.0 for tree in site.kept_trees())


def _obstacle(kind: str, geometry: LineString, outer_radius_m: float | None = None) -> Obstacle:
    return Obstacle(
        kind=kind,
        geometry=geometry,
        layer=f"synthetic_{kind}",
        source_name=SYNTHETIC_SOURCE,
        evidence=NETWORK_EVIDENCE,
        outer_radius_m=outer_radius_m,
    )


def _planting(position: Point, target: str) -> ReferencePlanting:
    is_tree = target == TREE
    return ReferencePlanting(
        position=position,
        target=target,
        plant_type=TREE_TYPE if is_tree else SHRUB_TYPE,
        species_ru=TREE_SPECIES if is_tree else SHRUB_SPECIES,
        layer=f"synthetic_{target}",
        scheme_id=SYNTHETIC_SCHEME,
    )
