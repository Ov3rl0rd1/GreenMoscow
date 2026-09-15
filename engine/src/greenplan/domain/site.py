from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

EXISTING_STATUS = "existing"
PROJECTED_STATUS = "projected"
KEEP_TREE_STATUS = "keep"
REMOVE_TREE_STATUS = "remove"
BOUNDARY_GAP_CLOSED = "boundary_gap_closed"
BOUNDARY_PIECES_JOINED = "boundary_pieces_joined"
BOUNDARY_SELF_INTERSECTION_FIXED = "boundary_self_intersection_fixed"


@dataclass(frozen=True, slots=True)
class Obstacle:
    kind: str
    geometry: BaseGeometry
    layer: str
    source_name: str
    evidence: tuple[str, ...]
    outer_radius_m: float | None = None
    status: str = EXISTING_STATUS
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ExistingTree:
    position: Point
    status: str
    layer: str
    source_name: str


@dataclass(frozen=True, slots=True)
class BoundaryRepair:
    code: str
    distance_m: float


@dataclass(frozen=True, slots=True)
class SiteDiagnostics:
    obstacle_counts: dict[str, int] = field(default_factory=dict)
    unknown_layers: tuple[str, ...] = ()
    unresolved_references: tuple[str, ...] = ()
    boundary_source: str = ""
    lawn_source: str = ""
    annotated_network_share: float = 0.0
    warnings: tuple[str, ...] = ()
    boundary_repairs: tuple[BoundaryRepair, ...] = ()


@dataclass(frozen=True, slots=True)
class SiteModel:
    boundary: Polygon | MultiPolygon
    plantable_surface: Polygon | MultiPolygon
    obstacles: tuple[Obstacle, ...]
    existing_trees: tuple[ExistingTree, ...]
    street_axes: tuple[LineString, ...]
    diagnostics: SiteDiagnostics

    def obstacles_of(self, kind: str) -> tuple[Obstacle, ...]:
        return tuple(obstacle for obstacle in self.obstacles if obstacle.kind == kind)

    def kept_trees(self) -> tuple[ExistingTree, ...]:
        return tuple(tree for tree in self.existing_trees if tree.status != "remove")
