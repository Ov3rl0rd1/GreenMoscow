from dataclasses import dataclass
from pathlib import Path

from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from matplotlib.patches import Polygon as PolygonPatch
from shapely.geometry.base import BaseGeometry

from greenplan.domain.decisions import CONDITIONALLY_ACCEPTED
from greenplan.domain.norms import TREE
from greenplan.domain.obstacle_kinds import UNDERGROUND_NETWORK_KINDS
from greenplan.domain.site import SiteModel
from greenplan.explain.report_model import PlantingReport
from greenplan.geometry.shapes import linear_parts, polygonal_parts
from greenplan.placement.planting_zones import PlantingZones


@dataclass(frozen=True, slots=True)
class PreviewSettings:
    figure_size_in: float = 14.0
    dpi: int = 120
    plantable_color: str = "#d9f0d3"
    restricted_color: str = "#f4b6b6"
    conditional_color: str = "#fde0a8"
    network_color: str = "#8a8a8a"
    boundary_color: str = "#222222"
    tree_color: str = "#1b7837"
    conditional_tree_color: str = "#e08214"
    shrub_color: str = "#762a83"
    rejection_color: str = "#d73027"
    network_line_width: float = 0.3
    boundary_line_width: float = 0.8
    shrub_marker_size: float = 2.0
    rejection_marker_size: float = 10.0


class PreviewRenderer:
    def __init__(self, settings: PreviewSettings) -> None:
        self._settings = settings

    def render(self, site: SiteModel, zones: PlantingZones, report: PlantingReport, path: Path) -> Path:
        settings = self._settings
        figure = Figure(figsize=(settings.figure_size_in, settings.figure_size_in), dpi=settings.dpi)
        FigureCanvasAgg(figure)
        axis = figure.add_subplot()
        self._draw_areas(axis, site, zones)
        self._draw_networks(axis, site)
        self._draw_plants(axis, report)
        self._draw_rejections(axis, report)
        self._frame(axis, site)
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path)
        return path

    def _draw_areas(self, axis: Axes, site: SiteModel, zones: PlantingZones) -> None:
        settings = self._settings
        plantable = site.plantable_surface
        _fill(axis, plantable, settings.plantable_color)
        _fill(axis, plantable.intersection(zones.conditional), settings.conditional_color)
        _fill(axis, plantable.intersection(zones.prohibited), settings.restricted_color)
        boundary = [list(polygon.exterior.coords) for polygon in polygonal_parts(site.boundary)]
        axis.add_collection(
            LineCollection(boundary, colors=settings.boundary_color, linewidths=settings.boundary_line_width)
        )

    def _draw_networks(self, axis: Axes, site: SiteModel) -> None:
        segments = [
            list(line.coords)
            for obstacle in site.obstacles
            if obstacle.kind in UNDERGROUND_NETWORK_KINDS
            for line in linear_parts(obstacle.geometry)
        ]
        axis.add_collection(
            LineCollection(
                segments, colors=self._settings.network_color, linewidths=self._settings.network_line_width
            )
        )

    def _draw_plants(self, axis: Axes, report: PlantingReport) -> None:
        settings = self._settings
        crowns = [
            Circle(
                (plant.x, plant.y),
                plant.crown_diameter_m / 2,
                fill=False,
                edgecolor=settings.conditional_tree_color
                if plant.status == CONDITIONALLY_ACCEPTED
                else settings.tree_color,
            )
            for plant in report.plants
            if plant.plant_type == TREE
        ]
        axis.add_collection(PatchCollection(crowns, match_original=True))
        shrubs = [plant for plant in report.plants if plant.plant_type != TREE]
        axis.scatter(
            [plant.x for plant in shrubs],
            [plant.y for plant in shrubs],
            s=settings.shrub_marker_size,
            color=settings.shrub_color,
        )

    def _draw_rejections(self, axis: Axes, report: PlantingReport) -> None:
        axis.scatter(
            [rejection.x for rejection in report.rejections],
            [rejection.y for rejection in report.rejections],
            s=self._settings.rejection_marker_size,
            color=self._settings.rejection_color,
            marker="x",
        )

    def _frame(self, axis: Axes, site: SiteModel) -> None:
        if not site.boundary.is_empty:
            min_x, min_y, max_x, max_y = site.boundary.bounds
            axis.set_xlim(min_x, max_x)
            axis.set_ylim(min_y, max_y)
        axis.set_aspect("equal")
        axis.set_axis_off()


def _fill(axis: Axes, area: BaseGeometry, color: str) -> None:
    patches = [PolygonPatch(list(polygon.exterior.coords)) for polygon in polygonal_parts(area)]
    axis.add_collection(PatchCollection(patches, facecolor=color, edgecolor="none"))
