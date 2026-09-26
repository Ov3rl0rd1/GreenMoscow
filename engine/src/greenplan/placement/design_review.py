from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil

import numpy as np
import shapely
from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, substring, unary_union
from shapely.strtree import STRtree

from greenplan.domain.composition import GROUP, CompositionElement
from greenplan.domain.decisions import PlantingDecision
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE, SIDEWALK_EDGE
from greenplan.domain.site import SiteModel
from greenplan.geometry.shapes import linear_parts, outline_lines

UNSHELTERED_FRONT = "unsheltered_front"
UNSHADED_SIDEWALK = "unshaded_sidewalk"
EMPTY_LAWN = "empty_lawn"
BARE_TREE_GROUP = "bare_tree_group"


@dataclass(frozen=True, slots=True)
class ReviewSettings:
    edge_piece_m: float = 25.0
    min_edge_piece_m: float = 12.0
    edge_site_margin_m: float = 10.0
    front_tree_reach_m: float = 10.0
    front_shrub_reach_m: float = 3.0
    front_band_m: float = 8.0
    front_priority: float = 3.0
    sidewalk_shade_margin_m: float = 1.0
    sidewalk_shaded_share: float = 0.3
    sidewalk_band_m: float = 6.0
    sidewalk_priority: float = 2.0
    tile_m: float = 30.0
    empty_tile_min_m2: float = 250.0
    empty_plant_reach_m: float = 3.0
    empty_priority: float = 1.5
    underplanting_reach_m: float = 5.0
    underplanting_priority: float = 1.8
    min_band_lawn_m2: float = 15.0


@dataclass(frozen=True, slots=True)
class DesignProblem:
    kind: str
    area: BaseGeometry
    guide: BaseGeometry | None
    measure: float
    priority: float
    element_id: str = ""


@dataclass(frozen=True, slots=True, eq=False)
class PlanSnapshot:
    trees: Sequence[PlantingDecision]
    shrubs: Sequence[PlantingDecision]
    elements: Sequence[CompositionElement]


class DesignReviewer:
    def __init__(self, settings: ReviewSettings | None = None) -> None:
        self._settings = settings or ReviewSettings()

    def review(self, site: SiteModel, plan: PlanSnapshot) -> list[DesignProblem]:
        lawn = site.plantable_surface
        if lawn.is_empty:
            return []
        trees = positions(plan.trees)
        shrubs = positions(plan.shrubs)
        problems = [
            *self._fronts(site, lawn, trees, shrubs),
            *self._sidewalks(site, lawn, plan.trees),
            *self._empty_tiles(lawn, trees + shrubs),
            *self._bare_groups(lawn, plan, shrubs),
        ]
        return sorted(problems, key=lambda problem: (-problem.priority, -problem.measure))

    def _fronts(
        self, site: SiteModel, lawn: BaseGeometry, trees: list[Point], shrubs: list[Point]
    ) -> list[DesignProblem]:
        settings = self._settings
        tree_index = STRtree(trees) if trees else None
        shrub_index = STRtree(shrubs) if shrubs else None
        found = []
        for piece in self._edge_pieces(site, CARRIAGEWAY_EDGE):
            if near(tree_index, piece, settings.front_tree_reach_m) or near(
                shrub_index, piece, settings.front_shrub_reach_m
            ):
                continue
            band = piece.buffer(settings.front_band_m).intersection(lawn)
            if band.area >= settings.min_band_lawn_m2:
                found.append(
                    DesignProblem(UNSHELTERED_FRONT, band, piece, piece.length, settings.front_priority)
                )
        return found

    def _sidewalks(
        self, site: SiteModel, lawn: BaseGeometry, trees: Sequence[PlantingDecision]
    ) -> list[DesignProblem]:
        settings = self._settings
        crowns = shapely.union_all(
            [
                decision.candidate.position.buffer(
                    decision.candidate.crown_diameter_m / 2 + settings.sidewalk_shade_margin_m
                )
                for decision in trees
            ]
        )
        found = []
        for piece in self._edge_pieces(site, SIDEWALK_EDGE):
            shaded = piece.intersection(crowns).length / piece.length if not crowns.is_empty else 0.0
            if shaded >= settings.sidewalk_shaded_share:
                continue
            band = piece.buffer(settings.sidewalk_band_m).intersection(lawn)
            if band.area >= settings.min_band_lawn_m2:
                found.append(
                    DesignProblem(UNSHADED_SIDEWALK, band, piece, piece.length, settings.sidewalk_priority)
                )
        return found

    def _empty_tiles(self, lawn: BaseGeometry, plants: list[Point]) -> list[DesignProblem]:
        settings = self._settings
        index = STRtree(plants) if plants else None
        min_x, min_y, max_x, max_y = lawn.bounds
        found = []
        for x in np.arange(min_x, max_x, settings.tile_m):
            for y in np.arange(min_y, max_y, settings.tile_m):
                tile = box(x, y, x + settings.tile_m, y + settings.tile_m).intersection(lawn)
                if tile.area < settings.empty_tile_min_m2:
                    continue
                if near(index, tile, settings.empty_plant_reach_m):
                    continue
                found.append(DesignProblem(EMPTY_LAWN, tile, None, tile.area, settings.empty_priority))
        return found

    def _bare_groups(
        self, lawn: BaseGeometry, plan: PlanSnapshot, shrubs: list[Point]
    ) -> list[DesignProblem]:
        settings = self._settings
        index = STRtree(shrubs) if shrubs else None
        members: dict[str, list[Point]] = {}
        for decision in plan.trees:
            members.setdefault(decision.candidate.element_id, []).append(decision.candidate.position)
        found = []
        for element in plan.elements:
            if element.kind != GROUP or element.element_id not in members:
                continue
            group = shapely.union_all(
                [point.buffer(settings.underplanting_reach_m) for point in members[element.element_id]]
            )
            if near(index, group, 0.0):
                continue
            area = group.intersection(lawn)
            if area.area >= settings.min_band_lawn_m2:
                found.append(
                    DesignProblem(
                        BARE_TREE_GROUP,
                        area,
                        None,
                        area.area,
                        settings.underplanting_priority,
                        element.element_id,
                    )
                )
        return found

    def _edge_pieces(self, site: SiteModel, kind: str) -> list[LineString]:
        settings = self._settings
        reach = site.boundary.buffer(settings.edge_site_margin_m)
        lines = [
            line
            for obstacle in site.obstacles_of(kind)
            for line in outline_lines(obstacle.geometry.intersection(reach))
        ]
        if not lines:
            return []
        merged = linemerge(linear_parts(unary_union(lines)))
        return [
            piece
            for line in linear_parts(merged)
            for piece in split_line(line, settings.edge_piece_m, settings.min_edge_piece_m)
        ]


def positions(decisions: Sequence[PlantingDecision]) -> list[Point]:
    return [decision.candidate.position for decision in decisions]


def near(index: STRtree | None, geometry: BaseGeometry, distance_m: float) -> bool:
    if index is None:
        return False
    return len(index.query(geometry, predicate="dwithin", distance=distance_m)) > 0


def split_line(line: LineString, piece_m: float, min_piece_m: float) -> list[LineString]:
    if line.length < min_piece_m:
        return []
    count = max(1, ceil(line.length / piece_m))
    step = line.length / count
    return [substring(line, index * step, (index + 1) * step) for index in range(count)]
