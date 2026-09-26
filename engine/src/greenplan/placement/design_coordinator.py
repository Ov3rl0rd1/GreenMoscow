from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from math import ceil, pi

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from greenplan.domain.composition import GROUP, HEDGE, ROW, SHRUB_GROUP, SOLITARY, CompositionElement
from greenplan.domain.decisions import PlantingDecision
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.geometry.shapes import linear_parts
from greenplan.placement.composition_planner import (
    GAP_TOLERANCE,
    LINE_SPACING_MARGIN,
    CompositionField,
    PlantLayout,
    Trial,
    best_variant,
    contiguous,
    shrub_shapes,
)
from greenplan.placement.composition_settings import CompositionSettings
from greenplan.placement.composition_shapes import evenly_spaced, group_shape
from greenplan.placement.design_review import (
    BARE_TREE_GROUP,
    EMPTY_LAWN,
    UNSHADED_SIDEWALK,
    UNSHELTERED_FRONT,
    DesignProblem,
    DesignReviewer,
    PlanSnapshot,
)
from greenplan.placement.peak_selector import SpatialHash

AGENT_PREFIX = "a"
SEED_STEP_M = 1.0


@dataclass(frozen=True, slots=True)
class CoordinatorSettings:
    enabled: bool = True
    max_rounds: int = 3
    seeds_per_problem: int = 120
    front_line_reach_m: float = 9.0
    front_hedge_min_size: int = 4
    group_min_filled_share: float = 0.67
    clump_min_filled_share: float = 0.6


@dataclass(frozen=True, slots=True, eq=False)
class TargetContext:
    field: CompositionField
    trial: Trial
    spacing_m: float
    budget: int


@dataclass(frozen=True, slots=True)
class DesignResolution:
    problem: str
    measure: float
    element_kind: str
    planted: int
    element_id: str


@dataclass(frozen=True, slots=True, eq=False)
class CoordinationResult:
    trees: tuple[PlantingDecision, ...]
    shrubs: tuple[PlantingDecision, ...]
    elements: tuple[CompositionElement, ...]
    journal: tuple[DesignResolution, ...]


class _GuardedTrial:
    def __init__(self, trial: Trial, others: Sequence[Point], clearance_m: float) -> None:
        self._trial = trial
        self._clearance_m = clearance_m
        self._others = SpatialHash(max(clearance_m, 1.0))
        for point in others:
            self.add(point)

    def add(self, point: Point) -> None:
        self._others.add(point.x, point.y)

    def __call__(self, point: Point) -> PlantingDecision | None:
        if self._others.has_point_closer_than(point.x, point.y, self._clearance_m):
            return None
        return self._trial(point)


class DesignCoordinator:
    def __init__(
        self,
        reviewer: DesignReviewer,
        composition: CompositionSettings,
        settings: CoordinatorSettings | None = None,
    ) -> None:
        self._reviewer = reviewer
        self._composition = composition
        self._settings = settings or CoordinatorSettings()

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    def improve(
        self,
        site: SiteModel,
        snapshot: PlanSnapshot,
        tree: TargetContext,
        shrub: TargetContext,
        shrub_tree_clearance_m: float,
    ) -> CoordinationResult:
        composition = self._composition
        tree_positions = [decision.candidate.position for decision in snapshot.trees]
        shrub_positions = [decision.candidate.position for decision in snapshot.shrubs]
        shrub_trial = _GuardedTrial(shrub.trial, tree_positions, shrub_tree_clearance_m)
        tree_trial = _GuardedTrial(tree.trial, shrub_positions, shrub_tree_clearance_m)
        trees = PlantLayout(
            tree.field,
            tree_trial,
            TREE,
            max(composition.tree_group_gap_m, composition.solitary_gap_m),
            AGENT_PREFIX,
            tree_positions,
        )
        shrubs = PlantLayout(
            shrub.field,
            shrub_trial,
            SHRUB,
            max(composition.shrub_group_gap_m, shrub.spacing_m),
            AGENT_PREFIX,
            shrub_positions,
        )
        session = _Session(self, site, tree, shrub, trees, shrubs, (tree_trial, shrub_trial))
        attempted: set[tuple[str, int, int]] = set()
        for _round in range(self._settings.max_rounds):
            current = PlanSnapshot(
                (*snapshot.trees, *trees.decisions),
                (*snapshot.shrubs, *shrubs.decisions),
                (*snapshot.elements, *trees.elements, *shrubs.elements),
            )
            fresh = [
                problem
                for problem in self._reviewer.review(site, current)
                if problem_key(problem) not in attempted
            ]
            if not fresh or session.exhausted():
                break
            for problem in fresh:
                attempted.add(problem_key(problem))
                if session.exhausted():
                    break
                session.solve(problem)
        return CoordinationResult(
            tuple(trees.decisions),
            tuple(shrubs.decisions),
            (*trees.elements, *shrubs.elements),
            tuple(session.journal),
        )


class _Session:
    def __init__(
        self,
        coordinator: DesignCoordinator,
        site: SiteModel,
        tree: TargetContext,
        shrub: TargetContext,
        trees: PlantLayout,
        shrubs: PlantLayout,
        guards: tuple[_GuardedTrial, _GuardedTrial],
    ) -> None:
        self._composition = coordinator._composition
        self._settings = coordinator._settings
        self._site = site
        self._tree = tree
        self._shrub = shrub
        self._trees = trees
        self._shrubs = shrubs
        self._tree_guard, self._shrub_guard = guards
        self.journal: list[DesignResolution] = []

    def exhausted(self) -> bool:
        return self._tree_room() <= 0 and self._shrub_room() <= 0

    def solve(self, problem: DesignProblem) -> None:
        solvers: dict[str, Callable[[DesignProblem], list[CompositionElement | None]]] = {
            UNSHELTERED_FRONT: self._shelter_front,
            UNSHADED_SIDEWALK: self._shade_sidewalk,
            EMPTY_LAWN: self._fill_lawn,
            BARE_TREE_GROUP: self._underplant,
        }
        for element in solvers[problem.kind](problem):
            if element is not None:
                self.journal.append(
                    DesignResolution(
                        problem.kind,
                        round(problem.measure, 1),
                        element.kind,
                        element.size,
                        element.element_id,
                    )
                )

    def _shelter_front(self, problem: DesignProblem) -> list[CompositionElement | None]:
        composition = self._composition
        lines = self._lawn_lines_near(problem)
        hedge = self._line_element(
            self._shrubs,
            self._shrub.field,
            lines,
            composition.hedge_offsets_m,
            self._shrub.spacing_m,
            self._shrub.spacing_m,
            self._settings.front_hedge_min_size,
            self._shrub_room(),
            HEDGE,
            problem,
        )
        if hedge is not None:
            return [hedge]
        return [self._tree_row(problem, lines)]

    def _shade_sidewalk(self, problem: DesignProblem) -> list[CompositionElement | None]:
        return [self._tree_row(problem, self._lawn_lines_near(problem))]

    def _fill_lawn(self, problem: DesignProblem) -> list[CompositionElement | None]:
        group = self._tree_group(problem)
        if group is None and self._tree_room() > 0:
            group = self._solitary(problem)
        return [group, self._clump(problem)]

    def _underplant(self, problem: DesignProblem) -> list[CompositionElement | None]:
        return [self._clump(problem)]

    def _tree_row(self, problem: DesignProblem, lines: Sequence[LineString]) -> CompositionElement | None:
        composition = self._composition
        row = self._line_element(
            self._trees,
            self._tree.field,
            lines,
            composition.tree_row_offsets_m,
            max(composition.tree_row_spacing_m, self._tree.spacing_m),
            self._tree.spacing_m,
            composition.tree_row_min_size,
            self._tree_room(),
            ROW,
            problem,
        )
        return row

    def _tree_group(self, problem: DesignProblem) -> CompositionElement | None:
        composition = self._composition
        within = region_test(problem.area)
        spacing = self._tree.spacing_m * LINE_SPACING_MARGIN
        for seed in self._seeds(self._tree.field, problem.area):
            if not self._trees.fits(seed, composition.tree_group_gap_m):
                continue
            for size in (size for size in composition.tree_group_sizes if size <= self._tree_room()):
                best = self._best_shape(seed, size, spacing, within)
                if len(best) >= ceil(size * self._settings.group_min_filled_share):
                    element = self._commit(self._trees, best, GROUP, self._tree.spacing_m)
                    return element
        return None

    def _best_shape(
        self, seed: Point, size: int, spacing_m: float, within: Callable[[Point], bool]
    ) -> list[PlantingDecision]:
        rotations = self._composition.tree_group_rotations
        best: list[PlantingDecision] = []
        for step in range(rotations):
            shape = group_shape(seed, size, spacing_m, 2 * pi * step / (rotations * size))
            accepted = self._trees.attempt(shape, self._tree.spacing_m, open_cells=True, within=within)
            if len(accepted) > len(best):
                best = accepted
            if len(best) == size:
                break
        return best

    def _solitary(self, problem: DesignProblem) -> CompositionElement | None:
        within = region_test(problem.area)
        for seed in self._seeds(self._tree.field, problem.area):
            if not self._trees.fits(seed, self._composition.solitary_gap_m):
                continue
            accepted = self._trees.attempt([seed], self._tree.spacing_m, open_cells=True, within=within)
            if accepted:
                element = self._commit(self._trees, accepted, SOLITARY, self._tree.spacing_m)
                return element
        return None

    def _clump(self, problem: DesignProblem) -> CompositionElement | None:
        composition = self._composition
        within = region_test(problem.area)
        spacing = self._shrub.spacing_m * LINE_SPACING_MARGIN
        for seed in self._seeds(self._shrub.field, problem.area):
            if not self._shrubs.fits(seed, composition.shrub_group_gap_m):
                continue
            clearance = self._shrub.field.clearance_at(seed)
            for variants in shrub_shapes(seed, spacing, composition, clearance, self._shrub_room()):
                needed = ceil(len(variants[0]) * self._settings.clump_min_filled_share)
                accepted = best_variant(self._shrubs, variants, self._shrub.spacing_m, needed, within)
                if len(accepted) >= needed:
                    return self._commit(self._shrubs, accepted, SHRUB_GROUP, self._shrub.spacing_m)
        return None

    def _line_element(
        self,
        layout: PlantLayout,
        field: CompositionField,
        lines: Sequence[LineString],
        offsets_m: Sequence[float],
        line_spacing_m: float,
        min_spacing_m: float,
        min_size: int,
        room: int,
        kind: str,
        problem: DesignProblem,
    ) -> CompositionElement | None:
        if room < min_size:
            return None
        within = region_test(problem.area)
        step = max(line_spacing_m, min_spacing_m * LINE_SPACING_MARGIN)
        best: list[PlantingDecision] = []
        for points in shifted_points(lines, offsets_m, step):
            accepted = layout.attempt(points[:room], min_spacing_m, open_cells=True, within=within)
            for segment in contiguous(accepted, step * GAP_TOLERANCE):
                if len(segment) > len(best):
                    best = segment
        if len(best) < min_size:
            return None
        middle = best[len(best) // 2].candidate.position
        return self._commit(layout, best, kind, step, field.edge_kind_at(middle))

    def _lawn_lines_near(self, problem: DesignProblem) -> list[LineString]:
        reach = (problem.guide or problem.area).buffer(self._settings.front_line_reach_m)
        return [
            part
            for edge in self._tree.field.edges
            for part in linear_parts(edge.line.intersection(reach))
            if part.length > 0
        ]

    def _seeds(self, field: CompositionField, area: BaseGeometry) -> list[Point]:
        min_x, min_y, max_x, max_y = area.bounds
        xs, ys = np.meshgrid(np.arange(min_x, max_x, SEED_STEP_M), np.arange(min_y, max_y, SEED_STEP_M))
        xs, ys = xs.ravel(), ys.ravel()
        inside = shapely.contains_xy(area, xs, ys) if xs.size else np.zeros(0, dtype=bool)
        points = [Point(x, y) for x, y in zip(xs[inside], ys[inside], strict=True)]
        usable = [point for point in points if field.is_open(point)]
        usable.sort(key=lambda point: -field.score_at(point))
        return usable[: self._settings.seeds_per_problem]

    def _commit(
        self,
        layout: PlantLayout,
        decisions: Sequence[PlantingDecision],
        kind: str,
        spacing_m: float,
        edge_kind: str = "",
    ) -> CompositionElement:
        element = layout.commit(decisions, kind, spacing_m, edge_kind)
        opposite = self._shrub_guard if layout is self._trees else self._tree_guard
        for decision in decisions:
            opposite.add(decision.candidate.position)
        return element

    def _tree_room(self) -> int:
        return self._tree.budget - self._trees.count

    def _shrub_room(self) -> int:
        return self._shrub.budget - self._shrubs.count


def shifted_points(
    lines: Sequence[LineString], offsets_m: Sequence[float], step_m: float
) -> Iterator[list[Point]]:
    for line in lines:
        for offset in offsets_m:
            for side in (1.0, -1.0):
                for part in linear_parts(line.offset_curve(side * offset)):
                    points = list(evenly_spaced(part, step_m))
                    if points:
                        yield points


def region_test(area: BaseGeometry) -> Callable[[Point], bool]:
    shapely.prepare(area)
    return lambda point: bool(area.contains(point))


def problem_key(problem: DesignProblem) -> tuple[str, int, int]:
    center = problem.area.representative_point()
    return problem.kind, int(center.x // 5), int(center.y // 5)
