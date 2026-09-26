from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from greenplan.domain.norms import SHRUB, TREE
from greenplan_ml.feature_channels import PLANTABLE_CHANNEL_INDEX
from greenplan_ml.plan_similarity import REPORT_NAME, planned_positions, reference_positions
from greenplan_ml.sample_store import StoredObject

REFERENCE_TITLE = "Проектное решение (эталон)"
FIGURE_SUFFIX = "_compare.png"


@dataclass(frozen=True, slots=True)
class FigureSettings:
    width_in: float = 16.0
    dpi: int = 110
    margin_m: float = 10.0
    lawn_color: str = "#a8dba0"
    tree_color: str = "#1b7837"
    shrub_color: str = "#7b3294"
    tree_marker: float = 40.0
    shrub_marker: float = 1.5


@dataclass(frozen=True, slots=True)
class PlanPanel:
    title: str
    trees: np.ndarray
    shrubs: np.ndarray


def reference_panel(stored: StoredObject) -> PlanPanel:
    return PlanPanel(REFERENCE_TITLE, reference_positions(stored, TREE), reference_positions(stored, SHRUB))


def run_panel(title: str, report_path: Path) -> PlanPanel:
    return PlanPanel(title, planned_positions(report_path, TREE), planned_positions(report_path, SHRUB))


class ComparisonFigure:
    def __init__(self, settings: FigureSettings | None = None) -> None:
        self._settings = settings or FigureSettings()

    def render(self, stored: StoredObject, panels: Sequence[PlanPanel], path: Path) -> Path:
        settings = self._settings
        grid = stored.meta.grid
        lawn = np.asarray(stored.features[PLANTABLE_CHANNEL_INDEX], dtype=np.float32) > 0.5
        bounds = lawn_bounds(lawn, grid, settings.margin_m)
        width, height = bounds[1] - bounds[0], bounds[3] - bounds[2]
        figure = Figure(
            figsize=(settings.width_in, settings.width_in * height / width * len(panels) + 1),
            dpi=settings.dpi,
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots(len(panels), 1, squeeze=False)[:, 0]
        extent = (
            grid.origin_x,
            grid.origin_x + grid.columns * grid.cell_size_m,
            grid.origin_y,
            grid.origin_y + grid.rows * grid.cell_size_m,
        )
        for axis, panel in zip(axes, panels, strict=True):
            self._draw(axis, panel, lawn, extent, bounds)
        figure.tight_layout()
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path)
        return path

    def _draw(
        self,
        axis: Axes,
        panel: PlanPanel,
        lawn: np.ndarray,
        extent: tuple[float, float, float, float],
        bounds: tuple[float, float, float, float],
    ) -> None:
        settings = self._settings
        axis.imshow(
            np.where(lawn, 1.0, np.nan),
            extent=extent,
            origin="lower",
            cmap="Greens",
            vmin=0.0,
            vmax=3.0,
            interpolation="nearest",
        )
        if len(panel.shrubs):
            axis.scatter(
                panel.shrubs[:, 0],
                panel.shrubs[:, 1],
                s=settings.shrub_marker,
                color=settings.shrub_color,
                label=f"кустарник: {len(panel.shrubs)}",
            )
        if len(panel.trees):
            axis.scatter(
                panel.trees[:, 0],
                panel.trees[:, 1],
                s=settings.tree_marker,
                facecolors="none",
                edgecolors=settings.tree_color,
                linewidths=1.2,
                label=f"деревья: {len(panel.trees)}",
            )
        axis.set_xlim(bounds[0], bounds[1])
        axis.set_ylim(bounds[2], bounds[3])
        axis.set_aspect("equal")
        axis.set_title(panel.title, fontsize=13, loc="left")
        axis.set_xticks([])
        axis.set_yticks([])
        if len(panel.trees) or len(panel.shrubs):
            axis.legend(loc="upper right", fontsize=10)


def lawn_bounds(lawn: np.ndarray, grid, margin_m: float) -> tuple[float, float, float, float]:
    rows = np.nonzero(lawn.any(axis=1))[0]
    columns = np.nonzero(lawn.any(axis=0))[0]
    if not rows.size:
        return (
            grid.origin_x,
            grid.origin_x + grid.columns * grid.cell_size_m,
            grid.origin_y,
            grid.origin_y + grid.rows * grid.cell_size_m,
        )
    return (
        grid.origin_x + columns.min() * grid.cell_size_m - margin_m,
        grid.origin_x + (columns.max() + 1) * grid.cell_size_m + margin_m,
        grid.origin_y + rows.min() * grid.cell_size_m - margin_m,
        grid.origin_y + (rows.max() + 1) * grid.cell_size_m + margin_m,
    )


def comparison_panels(stored: StoredObject, runs: Sequence[tuple[str, Path]]) -> list[PlanPanel]:
    panels = [reference_panel(stored)]
    for title, root in runs:
        report = root / stored.meta.object_id / REPORT_NAME
        if report.is_file():
            panels.append(run_panel(title, report))
    return panels


def figure_path(directory: Path, object_id: str) -> Path:
    return directory / f"{object_id}{FIGURE_SUFFIX}"
