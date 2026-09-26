from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from math import atan2, ceil, floor, pi

import numpy as np
from shapely.geometry import Point

from greenplan.domain.composition import GROUP, HEDGE, ROW, SHRUB_GROUP, SOLITARY, CompositionElement
from greenplan.domain.decisions import ACCEPTED, PlantingDecision
from greenplan.placement.composition_settings import CompositionSettings
from greenplan.placement.composition_shapes import (
    EdgeLine,
    LinePoints,
    group_shape,
    hexagonal_patch,
    offset_lines,
)
from greenplan.placement.peak_selector import SpatialHash
from greenplan.placement.raster import RasterGrid

Trial = Callable[[Point], PlantingDecision | None]
EdgeKindOf = Callable[[Point], str]
GAP_TOLERANCE = 1.5
LINE_SPACING_MARGIN = 1.02
MAX_ROW_TURN_RAD = pi / 4


@dataclass(frozen=True, slots=True, eq=False)
class CompositionField:
    grid: RasterGrid
    score: np.ndarray
    eligible: np.ndarray
    lawn_clearance_m: np.ndarray
    edges: tuple[EdgeLine, ...]
    relaxed: np.ndarray | None = None
    edge_kind_of: EdgeKindOf | None = None
    open_cells: np.ndarray | None = None

    def edge_kind_at(self, point: Point) -> str:
        return self.edge_kind_of(point) if self.edge_kind_of is not None else ""

    def relaxed_field(self) -> "CompositionField":
        return self if self.relaxed is None else replace(self, eligible=self.relaxed, relaxed=None)

    def is_eligible(self, point: Point) -> bool:
        return self._lookup(self.eligible, point)

    def is_open(self, point: Point) -> bool:
        return self._lookup(self.eligible if self.open_cells is None else self.open_cells, point)

    def _lookup(self, mask: np.ndarray, point: Point) -> bool:
        row, column = self.grid.cell_of(point.x, point.y)
        inside = 0 <= row < self.grid.rows and 0 <= column < self.grid.columns
        return inside and bool(mask[row, column])

    def score_at(self, point: Point) -> float:
        row, column = self.grid.cell_of(point.x, point.y)
        if 0 <= row < self.grid.rows and 0 <= column < self.grid.columns:
            return float(self.score[row, column])
        return 0.0

    def seeds(self, limit: int, minimum_clearance_m: float = 0.0) -> Iterator[Point]:
        mask = self.eligible & (self.lawn_clearance_m >= minimum_clearance_m)
        rows, columns = np.nonzero(mask)
        if rows.size == 0:
            return
        scores = self.score[rows, columns]
        count = min(limit, scores.size)
        best = np.argpartition(-scores, count - 1)[:count]
        for index in best[np.argsort(-scores[best], kind="stable")]:
            yield Point(*self.grid.center_of(int(rows[index]), int(columns[index])))


@dataclass(frozen=True, slots=True)
class ComposedPlanting:
    decisions: tuple[PlantingDecision, ...]
    elements: tuple[CompositionElement, ...]


class PlantLayout:
    def __init__(
        self,
        field: CompositionField,
        trial: Trial,
        target: str,
        bucket_m: float,
        id_prefix: str = "",
        placed: Sequence[Point] = (),
    ) -> None:
        self._field = field
        self._trial = trial
        self._target = target
        self._id_prefix = id_prefix
        self._placed = SpatialHash(bucket_m)
        for point in placed:
            self._placed.add(point.x, point.y)
        self._strict = True
        self.decisions: list[PlantingDecision] = []
        self.elements: list[CompositionElement] = []

    def use(self, field: CompositionField) -> None:
        self._field = field
        self._strict = False

    @property
    def count(self) -> int:
        return len(self.decisions)

    def fits(self, point: Point, distance_m: float) -> bool:
        return not self._placed.has_point_closer_than(point.x, point.y, distance_m)

    def attempt(
        self,
        points: Sequence[Point],
        spacing_m: float,
        open_cells: bool = False,
        within: Callable[[Point], bool] | None = None,
    ) -> list[PlantingDecision]:
        accepted: list[PlantingDecision] = []
        usable = self._field.is_open if open_cells else self._field.is_eligible
        for point in points:
            if within is not None and not within(point):
                continue
            if not usable(point) or not self.fits(point, spacing_m):
                continue
            if any(point.distance(other.candidate.position) < spacing_m for other in accepted):
                continue
            decision = self._trial(point)
            if decision is not None and (not self._strict or decision.status == ACCEPTED):
                accepted.append(decision)
        return accepted

    def commit(
        self, decisions: Sequence[PlantingDecision], kind: str, spacing_m: float, edge_kind: str = ""
    ) -> CompositionElement:
        element_id = f"{self._target}-{kind}-{self._id_prefix}{len(self.elements) + 1:03d}"
        for decision in decisions:
            position = decision.candidate.position
            self._placed.add(position.x, position.y)
            self.decisions.append(
                replace(decision, candidate=replace(decision.candidate, element_id=element_id))
            )
        element = CompositionElement(element_id, kind, self._target, len(decisions), spacing_m, edge_kind)
        self.elements.append(element)
        return element

    def result(self) -> ComposedPlanting:
        return ComposedPlanting(tuple(self.decisions), tuple(self.elements))


class CompositionPlanner:
    def __init__(self, settings: CompositionSettings) -> None:
        self._settings = settings

    def compose_trees(
        self, field: CompositionField, trial: Trial, target: str, spacing_m: float, budget: int
    ) -> ComposedPlanting:
        settings = self._settings
        row_spacing = max(spacing_m, settings.tree_row_spacing_m)
        layout = PlantLayout(
            field, trial, target, max(settings.solitary_gap_m, settings.tree_group_gap_m, row_spacing)
        )
        self._lines(
            layout,
            field,
            settings.tree_row_offsets_m,
            row_spacing,
            spacing_m,
            settings.tree_row_min_size,
            floor(budget * settings.tree_row_budget_share),
            ROW,
        )
        self._tree_groups(layout, field, spacing_m, budget)
        settings = self._settings
        self._solitaires(
            layout, field, spacing_m, budget, settings.solitary_lawn_clearance_m, settings.solitary_gap_m
        )
        relaxed = field.relaxed_field()
        layout.use(relaxed)
        self._solitaires(layout, relaxed, spacing_m, budget, 0.0, settings.tree_group_gap_m)
        return layout.result()

    def compose_shrubs(
        self, field: CompositionField, trial: Trial, target: str, spacing_m: float, budget: int
    ) -> ComposedPlanting:
        settings = self._settings
        layout = PlantLayout(field, trial, target, max(settings.shrub_group_gap_m, spacing_m))
        self._lines(
            layout,
            field,
            settings.hedge_offsets_m,
            spacing_m,
            spacing_m,
            settings.hedge_min_size,
            floor(budget * settings.hedge_budget_share),
            HEDGE,
        )
        self._shrub_groups(layout, field, spacing_m, budget)
        relaxed = field.relaxed_field()
        layout.use(relaxed)
        self._shrub_groups(layout, relaxed, spacing_m, budget)
        return layout.result()

    def _lines(
        self,
        layout: PlantLayout,
        field: CompositionField,
        offsets_m: Sequence[float],
        line_spacing_m: float,
        min_spacing_m: float,
        min_size: int,
        budget: int,
        kind: str,
    ) -> None:
        step = max(line_spacing_m, min_spacing_m * LINE_SPACING_MARGIN)
        lines = offset_lines(field.edges, offsets_m, step)
        weights = dict(self._settings.line_edge_weights)
        for run in ranked_runs(field, lines, min_size, self._settings.line_confident_share, weights):
            remaining = budget - layout.count
            if remaining < min_size:
                return
            window = best_window(field, run.points, remaining)
            accepted = layout.attempt(window, min_spacing_m, open_cells=True)
            for segment in contiguous(accepted, step * GAP_TOLERANCE):
                if len(segment) >= min_size and layout.count + len(segment) <= budget:
                    middle = segment[len(segment) // 2].candidate.position
                    layout.commit(segment, kind, step, run.kind or field.edge_kind_at(middle))

    def _tree_groups(
        self, layout: PlantLayout, field: CompositionField, spacing_m: float, budget: int
    ) -> None:
        settings = self._settings
        for seed in field.seeds(budget * settings.seed_pool_factor):
            if layout.count >= budget:
                return
            if not layout.fits(seed, settings.tree_group_gap_m):
                continue
            for size in (size for size in settings.tree_group_sizes if size <= budget - layout.count):
                best = self._best_rotation(layout, seed, size, spacing_m)
                if len(best) >= ceil(size * settings.tree_group_min_filled_share):
                    layout.commit(best, GROUP, spacing_m)
                    break

    def _best_rotation(
        self, layout: PlantLayout, seed: Point, size: int, spacing_m: float
    ) -> list[PlantingDecision]:
        rotations = self._settings.tree_group_rotations
        best: list[PlantingDecision] = []
        for step in range(rotations):
            shape = group_shape(
                seed, size, spacing_m * LINE_SPACING_MARGIN, 2 * pi * step / (rotations * size)
            )
            accepted = layout.attempt(shape, spacing_m, open_cells=True)
            if len(accepted) > len(best):
                best = accepted
            if len(best) == size:
                break
        return best

    def _solitaires(
        self,
        layout: PlantLayout,
        field: CompositionField,
        spacing_m: float,
        budget: int,
        lawn_clearance_m: float,
        gap_m: float,
    ) -> None:
        seeds = field.seeds(budget * self._settings.seed_pool_factor, lawn_clearance_m)
        for seed in seeds:
            if layout.count >= budget:
                return
            if not layout.fits(seed, gap_m):
                continue
            accepted = layout.attempt([seed], spacing_m)
            if accepted:
                layout.commit(accepted, SOLITARY, spacing_m)

    def _shrub_groups(
        self, layout: PlantLayout, field: CompositionField, spacing_m: float, budget: int
    ) -> None:
        settings = self._settings
        for seed in field.seeds(budget * settings.seed_pool_factor):
            if layout.count >= budget:
                return
            if not layout.fits(seed, settings.shrub_group_gap_m):
                continue
            for patch in self._shrub_patches(seed, spacing_m):
                if len(patch) > budget - layout.count:
                    continue
                accepted = layout.attempt(patch, spacing_m, open_cells=True)
                if len(accepted) >= ceil(len(patch) * settings.shrub_group_min_filled_share):
                    layout.commit(accepted, SHRUB_GROUP, spacing_m)
                    break

    def _shrub_patches(self, seed: Point, spacing_m: float) -> Iterator[list[Point]]:
        settings = self._settings
        for rings in settings.shrub_group_rings:
            yield hexagonal_patch(seed, rings, spacing_m * LINE_SPACING_MARGIN)
        for size in settings.shrub_group_small_sizes:
            yield group_shape(seed, size, spacing_m * LINE_SPACING_MARGIN, 0.0)


def ranked_runs(
    field: CompositionField,
    lines: Iterator[LinePoints],
    min_size: int,
    confident_share: float,
    edge_weights: dict[str, float] | None = None,
) -> list[LinePoints]:
    weights = edge_weights or {}
    runs: list[tuple[float, LinePoints]] = []
    for line in lines:
        current: list[Point] = []
        for point in (*line.points, None):
            if point is not None and field.is_open(point) and not turns_sharply(current, point):
                current.append(point)
                continue
            confident = sum(1 for item in current if field.is_eligible(item))
            if len(current) >= min_size and confident >= confident_share * len(current):
                quality = sum(
                    field.score_at(item) * weights.get(line.kind or field.edge_kind_at(item), 1.0)
                    for item in current
                )
                runs.append((quality, LinePoints(tuple(current), line.kind)))
            current = [point] if point is not None and field.is_open(point) else []
    return [run for _quality, run in sorted(runs, key=lambda item: -item[0])]


def turns_sharply(current: Sequence[Point], point: Point) -> bool:
    if len(current) < 2:
        return False
    before = atan2(current[-1].y - current[-2].y, current[-1].x - current[-2].x)
    after = atan2(point.y - current[-1].y, point.x - current[-1].x)
    turn = abs((after - before + pi) % (2 * pi) - pi)
    return turn > MAX_ROW_TURN_RAD


def best_window(field: CompositionField, points: Sequence[Point], size: int) -> Sequence[Point]:
    if len(points) <= size:
        return points
    scores = np.array([field.score_at(point) for point in points])
    sums = np.convolve(scores, np.ones(size), mode="valid")
    start = int(np.argmax(sums))
    return points[start : start + size]


def contiguous(decisions: Sequence[PlantingDecision], max_step_m: float) -> list[list[PlantingDecision]]:
    segments: list[list[PlantingDecision]] = []
    for decision in decisions:
        position = decision.candidate.position
        if segments and segments[-1][-1].candidate.position.distance(position) <= max_step_m:
            segments[-1].append(decision)
        else:
            segments.append([decision])
    return segments
