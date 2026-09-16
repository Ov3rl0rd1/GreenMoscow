from pathlib import Path

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from greenplan.constraints.candidate_evaluator import CandidateEvaluator
from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.requirement_resolver import RequirementResolver
from greenplan.domain.site import ExistingTree, Obstacle, SiteDiagnostics, SiteModel
from greenplan.knowledge.norms_repository import NormsRepository


def network(kind: str, coordinates, outer_radius_m: float | None = None, layer: str = "network") -> Obstacle:
    return Obstacle(kind, LineString(coordinates), layer, "tile_up", (f"layer:{layer}",), outer_radius_m)


def point_obstacle(kind: str, x: float, y: float) -> Obstacle:
    return Obstacle(kind, Point(x, y), kind, "tile_tp", (f"layer:{kind}",))


def open_site(
    obstacles: tuple[Obstacle, ...],
    boundary: BaseGeometry | None = None,
    plantable: BaseGeometry | None = None,
    existing_trees: tuple[ExistingTree, ...] = (),
) -> SiteModel:
    area = boundary or Polygon([(-100, -100), (100, -100), (100, 100), (-100, 100)])
    return SiteModel(
        boundary=area,
        plantable_surface=plantable if plantable is not None else area,
        obstacles=obstacles,
        existing_trees=existing_trees,
        street_axes=(),
        diagnostics=SiteDiagnostics(),
    )


class NormsToolkit:
    def __init__(self, knowledge_root: Path, design: DesignConstraints | None = None) -> None:
        self.design = design or DesignConstraints()
        self.repository = NormsRepository.from_knowledge(knowledge_root)
        self.resolver = RequirementResolver(
            self.repository, self.design.unknown_overhead_voltage_kv, self.design.active_activations()
        )
        self.meter = ClearanceMeter(self.repository.defaults)

    def evaluator(self, site: SiteModel) -> CandidateEvaluator:
        return CandidateEvaluator(self.resolver, self.meter, site, self.design)


EMPTY_AREA = MultiPolygon()
