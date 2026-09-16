import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from shapely.geometry import Point, Polygon

from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteDiagnostics, SiteModel
from greenplan.placement.peak_selector import PeakSelector
from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan.placement.score_maps import ScoreMapProvider
from greenplan_ml.feature_channels import CARRIAGEWAY_CHANNEL_INDEX, PLANTABLE_CHANNEL_INDEX
from greenplan_ml.inference import OnnxHeatmapModel
from greenplan_ml.sample_store import (
    ALLOWED_MASK_INDEX,
    CONDITIONAL_MASK_INDEX,
    ObjectMeta,
    PlantingMeta,
    StoredObject,
)
from greenplan_ml.score_map import HEATMAP_CHANNEL_BY_TARGET

REPORT_FILE = "evaluation.json"
MARKDOWN_FILE = "evaluation.md"
RULE_SITE = SiteModel(Polygon(), Polygon(), (), (), (), SiteDiagnostics())
MODEL_SOURCE = "model"
BASELINE_SOURCE = "rules"


@dataclass(frozen=True, slots=True)
class EvaluationSettings:
    tolerances_m: tuple[float, ...] = (2.0, 3.0)
    tree_spacing_m: float = 5.0
    shrub_spacing_m: float = 1.0
    minimum_score: float = 0.05


@dataclass(frozen=True, slots=True)
class TargetMetrics:
    source: str
    target: str
    tolerance_m: float
    expected: int
    predicted: int
    matched: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True, slots=True)
class ObjectEvaluation:
    object_id: str
    level: str
    metrics: tuple[TargetMetrics, ...]
    crown_mae_m: float


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    objects: tuple[ObjectEvaluation, ...]
    totals: tuple[TargetMetrics, ...]

    def write(self, directory: Path) -> tuple[Path, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / REPORT_FILE
        json_path.write_text(
            json.dumps(
                {
                    "objects": [asdict(item) for item in self.objects],
                    "totals": [asdict(item) for item in self.totals],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        markdown_path = directory / MARKDOWN_FILE
        markdown_path.write_text(render_markdown(self), encoding="utf-8")
        return json_path, markdown_path


class ModelEvaluator:
    def __init__(
        self,
        model: OnnxHeatmapModel,
        rules: dict[str, ScoreMapProvider],
        settings: EvaluationSettings | None = None,
    ) -> None:
        self._model = model
        self._rules = rules
        self._settings = settings or EvaluationSettings()
        self._selector = PeakSelector()

    def evaluate(self, objects: Sequence[StoredObject]) -> EvaluationReport:
        evaluations = [self.evaluate_object(item) for item in objects]
        return EvaluationReport(tuple(evaluations), totals_of(evaluations))

    def evaluate_object(self, stored: StoredObject) -> ObjectEvaluation:
        meta = stored.meta
        grid = meta.grid.to_grid()
        features = np.asarray(stored.features, dtype=np.float32)
        raster = raster_from_features(features, np.asarray(stored.masks), grid, meta)
        heatmaps = self._model.predict(features)
        metrics: list[TargetMetrics] = []
        for target in (TREE, SHRUB):
            expected = meta.plantings_of(target)
            if not expected:
                continue
            heat = heatmaps[self._model.channel_index(HEATMAP_CHANNEL_BY_TARGET[target])]
            rule_score = self._rules[target].score(raster, RULE_SITE)
            metrics.extend(self._metrics(MODEL_SOURCE, target, grid, heat, raster, expected))
            metrics.extend(self._metrics(BASELINE_SOURCE, target, grid, rule_score, raster, expected))
        return ObjectEvaluation(
            meta.object_id, meta.level, tuple(metrics), self._crown_error(stored, heatmaps, grid)
        )

    def _metrics(
        self,
        source: str,
        target: str,
        grid: RasterGrid,
        score: np.ndarray,
        raster: SiteRaster,
        expected: Sequence[PlantingMeta],
    ) -> list[TargetMetrics]:
        eligible = raster.allowed & (score > self._settings.minimum_score)
        points = self._selector.select(grid, score, eligible, self._spacing(target), len(expected))
        return [
            _scored(source, target, tolerance, expected, points, matched_count(points, expected, tolerance))
            for tolerance in self._settings.tolerances_m
        ]

    def _spacing(self, target: str) -> float:
        return self._settings.tree_spacing_m if target == TREE else self._settings.shrub_spacing_m

    def _crown_error(self, stored: StoredObject, heatmaps: np.ndarray, grid: RasterGrid) -> float:
        meta = stored.meta
        trees = meta.plantings_of(TREE)
        if not trees:
            return 0.0
        crown_index = self._model.channel_index("crown_diameter")
        predicted = heatmaps[crown_index]
        expected = np.asarray(stored.targets[meta.target_channels.index("crown_diameter")], dtype=np.float32)
        rows, columns = _cells_of(grid, trees)
        if not rows.size:
            return 0.0
        difference = np.abs(predicted[rows, columns] - expected[rows, columns])
        return float(difference.mean() * meta.scales.crown_saturation_m)


def raster_from_features(
    features: np.ndarray, masks: np.ndarray, grid: RasterGrid, meta: ObjectMeta
) -> SiteRaster:
    allowed = masks[ALLOWED_MASK_INDEX] > 0
    edge = features[CARRIAGEWAY_CHANNEL_INDEX] * meta.scales.max_distance_m
    return SiteRaster(
        grid=grid,
        plantable=features[PLANTABLE_CHANNEL_INDEX] > 0.5,
        allowed=allowed,
        conditional=masks[CONDITIONAL_MASK_INDEX] > 0,
        clearance_m=clearance_of(allowed, grid.cell_size_m),
        reference_edge_distance_m=np.where(edge < meta.scales.max_distance_m, edge, np.inf),
    )


def clearance_of(allowed: np.ndarray, cell_size_m: float) -> np.ndarray:
    padded = np.pad(allowed, 1, constant_values=False)
    return (distance_transform_edt(padded)[1:-1, 1:-1] * cell_size_m).astype(np.float32)


def matched_count(points: Sequence[Point], expected: Sequence[PlantingMeta], tolerance_m: float) -> int:
    if not points or not expected:
        return 0
    predicted = np.array([[point.x, point.y] for point in points], dtype=float)
    reference = np.array([[item.x, item.y] for item in expected], dtype=float)
    distances = np.linalg.norm(predicted[:, None, :] - reference[None, :, :], axis=2)
    taken = np.zeros(len(reference), dtype=bool)
    matched = 0
    for row in range(distances.shape[0]):
        candidates = np.where((distances[row] <= tolerance_m) & ~taken)[0]
        if candidates.size:
            nearest = candidates[int(np.argmin(distances[row, candidates]))]
            taken[nearest] = True
            matched += 1
    return matched


def totals_of(evaluations: Sequence[ObjectEvaluation]) -> tuple[TargetMetrics, ...]:
    grouped: dict[tuple[str, str, float], list[TargetMetrics]] = {}
    for evaluation in evaluations:
        for item in evaluation.metrics:
            grouped.setdefault((item.source, item.target, item.tolerance_m), []).append(item)
    totals = []
    for (source, target, tolerance), items in sorted(grouped.items()):
        expected = sum(item.expected for item in items)
        predicted = sum(item.predicted for item in items)
        matched = sum(item.matched for item in items)
        totals.append(_metrics_of(source, target, tolerance, expected, predicted, matched))
    return tuple(totals)


def render_markdown(report: EvaluationReport) -> str:
    lines = ["# Оценка модели размещения", "", "## Итого по всем объектам", ""]
    lines.extend(_markdown_table(report.totals))
    for evaluation in report.objects:
        lines.extend(["", f"## {evaluation.object_id} (уровень {evaluation.level})", ""])
        lines.append(f"Средняя ошибка диаметра кроны: {evaluation.crown_mae_m:.2f} м")
        lines.append("")
        lines.extend(_markdown_table(evaluation.metrics))
    return "\n".join(lines) + "\n"


def _markdown_table(metrics: Sequence[TargetMetrics]) -> list[str]:
    header = [
        "| источник | цель | допуск, м | эталон | предложено | совпало | точность | полнота | F1 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    rows = [
        f"| {item.source} | {item.target} | {item.tolerance_m:g} | {item.expected} | {item.predicted} | "
        f"{item.matched} | {item.precision:.3f} | {item.recall:.3f} | {item.f1:.3f} |"
        for item in metrics
    ]
    return header + rows


def _scored(
    source: str,
    target: str,
    tolerance_m: float,
    expected: Sequence[PlantingMeta],
    points: Sequence[Point],
    matched: int,
) -> TargetMetrics:
    return _metrics_of(source, target, tolerance_m, len(expected), len(points), matched)


def _metrics_of(
    source: str, target: str, tolerance_m: float, expected: int, predicted: int, matched: int
) -> TargetMetrics:
    precision = matched / predicted if predicted else 0.0
    recall = matched / expected if expected else 0.0
    denominator = precision + recall
    return TargetMetrics(
        source=source,
        target=target,
        tolerance_m=tolerance_m,
        expected=expected,
        predicted=predicted,
        matched=matched,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(2 * precision * recall / denominator if denominator else 0.0, 4),
    )


def _cells_of(grid: RasterGrid, plantings: Sequence[PlantingMeta]) -> tuple[np.ndarray, np.ndarray]:
    rows = np.array([int((item.y - grid.origin_y) // grid.cell_size_m) for item in plantings])
    columns = np.array([int((item.x - grid.origin_x) // grid.cell_size_m) for item in plantings])
    inside = (rows >= 0) & (rows < grid.rows) & (columns >= 0) & (columns < grid.columns)
    return rows[inside], columns[inside]
