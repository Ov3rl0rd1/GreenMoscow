import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from greenplan.domain.norms import SHRUB, TREE
from greenplan.placement.raster import RasterGrid
from greenplan_ml.feature_channels import PLANTABLE_CHANNEL_INDEX
from greenplan_ml.sample_store import StoredObject

REPORT_NAME = "planting_report.json"
REJECTED_STATUS = "rejected"
PLANTABLE_LEVEL = 0.5
SIMILARITY_JSON = "similarity.json"
SIMILARITY_MARKDOWN = "similarity.md"
TARGETS = (TREE, SHRUB)


@dataclass(frozen=True, slots=True)
class SimilaritySettings:
    tolerances_m: tuple[float, ...] = (3.0, 5.0)
    tree_group_link_m: float = 8.0
    row_reach_m: float = 12.0
    row_cosine: float = -0.94
    duplicate_tolerance_m: float = 0.6
    shrub_group_link_m: float = 1.6

    def link_for(self, target: str) -> float:
        return self.tree_group_link_m if target == TREE else self.shrub_group_link_m


@dataclass(frozen=True, slots=True)
class SimilarityMetrics:
    object_id: str
    source: str
    target: str
    reference: int
    planned: int
    count_ratio: float
    f1_by_tolerance: dict[str, float]
    chamfer_m: float
    reference_spacing_m: float
    planned_spacing_m: float
    reference_grouped_share: float
    planned_grouped_share: float
    reference_row_share: float = 0.0
    planned_row_share: float = 0.0


def planned_positions(report_path: Path, target: str) -> np.ndarray:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    points = [
        [plant["x"], plant["y"]]
        for plant in report["plants"]
        if plant["plant_type"] == target and plant["status"] != REJECTED_STATUS
    ]
    return np.array(points, dtype=float).reshape(-1, 2)


def reference_positions(stored: StoredObject, target: str) -> np.ndarray:
    points = np.array([[item.x, item.y] for item in stored.meta.plantings_of(target)], dtype=float)
    points = points.reshape(-1, 2)
    grid = stored.meta.grid.to_grid()
    rows, columns = cell_rows_and_columns(grid, points)
    inside = (rows >= 0) & (rows < grid.rows) & (columns >= 0) & (columns < grid.columns)
    on_lawn = np.zeros(len(points), dtype=bool)
    plantable = np.asarray(stored.features[PLANTABLE_CHANNEL_INDEX])
    on_lawn[inside] = plantable[rows[inside], columns[inside]] > PLANTABLE_LEVEL
    return points[on_lawn]


def cell_rows_and_columns(grid: RasterGrid, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    columns = np.floor((points[:, 0] - grid.origin_x) / grid.cell_size_m).astype(int)
    rows = np.floor((points[:, 1] - grid.origin_y) / grid.cell_size_m).astype(int)
    return rows, columns


def matched_pairs(planned: np.ndarray, reference: np.ndarray, tolerance_m: float) -> int:
    if not len(planned) or not len(reference):
        return 0
    distances, indices = cKDTree(reference).query(
        planned, k=min(8, len(reference)), distance_upper_bound=tolerance_m
    )
    distances = distances.reshape(len(planned), -1)
    indices = indices.reshape(len(planned), -1)
    order = np.argsort(distances[:, 0], kind="stable")
    taken: set[int] = set()
    for row in order:
        for distance, index in zip(distances[row], indices[row], strict=True):
            if np.isfinite(distance) and int(index) not in taken:
                taken.add(int(index))
                break
    return len(taken)


def f1_score(matched: int, planned: int, reference: int) -> float:
    precision = matched / planned if planned else 0.0
    recall = matched / reference if reference else 0.0
    total = precision + recall
    return round(2 * precision * recall / total, 4) if total else 0.0


def chamfer(planned: np.ndarray, reference: np.ndarray) -> float:
    if not len(planned) or not len(reference):
        return 0.0
    forward, _ = cKDTree(reference).query(planned)
    backward, _ = cKDTree(planned).query(reference)
    return round(float((forward.mean() + backward.mean()) / 2), 3)


def median_spacing(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    distances, _ = cKDTree(points).query(points, k=2)
    return round(float(np.median(distances[:, 1])), 2)


def row_share(points: np.ndarray, reach_m: float, cosine: float) -> float:
    if len(points) < 3:
        return 0.0
    index = cKDTree(points)
    in_row = 0
    for position, point in enumerate(points):
        neighbours = [other for other in index.query_ball_point(point, reach_m) if other != position]
        vectors = points[neighbours] - point
        lengths = np.linalg.norm(vectors, axis=1)
        directions = vectors[lengths > 0] / lengths[lengths > 0][:, None]
        in_row += bool(len(directions) >= 2 and ((directions @ directions.T) < cosine).any())
    return round(in_row / len(points), 3)


def without_duplicates(points: np.ndarray, tolerance_m: float) -> np.ndarray:
    if len(points) < 2:
        return points
    index = cKDTree(points)
    taken = np.zeros(len(points), dtype=bool)
    keep = []
    for position in range(len(points)):
        if taken[position]:
            continue
        taken[index.query_ball_point(points[position], tolerance_m)] = True
        keep.append(position)
    return points[keep]


def grouped_share(points: np.ndarray, link_m: float) -> float:
    if len(points) < 3:
        return 0.0
    neighbours = cKDTree(points).query_ball_point(points, link_m, return_length=True) - 1
    return round(float((neighbours >= 2).mean()), 3)


class PlanSimilarity:
    def __init__(self, settings: SimilaritySettings | None = None) -> None:
        self._settings = settings or SimilaritySettings()

    def _row_share(self, points: np.ndarray) -> float:
        settings = self._settings
        unique = without_duplicates(points, settings.duplicate_tolerance_m)
        return row_share(unique, settings.row_reach_m, settings.row_cosine)

    def compare(self, stored: StoredObject, source: str, report_path: Path) -> list[SimilarityMetrics]:
        return [self._target_metrics(stored, source, report_path, target) for target in TARGETS]

    def _target_metrics(
        self, stored: StoredObject, source: str, report_path: Path, target: str
    ) -> SimilarityMetrics:
        planned = planned_positions(report_path, target)
        reference = reference_positions(stored, target)
        link = self._settings.link_for(target)
        return SimilarityMetrics(
            object_id=stored.meta.object_id,
            source=source,
            target=target,
            reference=len(reference),
            planned=len(planned),
            count_ratio=round(len(planned) / len(reference), 3) if len(reference) else 0.0,
            f1_by_tolerance={
                f"{tolerance:g}": f1_score(
                    matched_pairs(planned, reference, tolerance), len(planned), len(reference)
                )
                for tolerance in self._settings.tolerances_m
            },
            chamfer_m=chamfer(planned, reference),
            reference_spacing_m=median_spacing(reference),
            planned_spacing_m=median_spacing(planned),
            reference_grouped_share=grouped_share(reference, link),
            planned_grouped_share=grouped_share(planned, link),
            reference_row_share=self._row_share(reference),
            planned_row_share=self._row_share(planned),
        )


def compare_runs(
    objects: Sequence[StoredObject], runs: Mapping[str, Path], similarity: PlanSimilarity | None = None
) -> list[SimilarityMetrics]:
    comparer = similarity or PlanSimilarity()
    metrics: list[SimilarityMetrics] = []
    for stored in objects:
        for source, root in runs.items():
            report = root / stored.meta.object_id / REPORT_NAME
            if report.is_file():
                metrics.extend(comparer.compare(stored, source, report))
    return metrics


def write_similarity(metrics: Sequence[SimilarityMetrics], directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / SIMILARITY_JSON
    json_path.write_text(
        json.dumps([asdict(item) for item in metrics], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_path = directory / SIMILARITY_MARKDOWN
    markdown_path.write_text(similarity_markdown(metrics), encoding="utf-8")
    return json_path, markdown_path


def similarity_markdown(metrics: Sequence[SimilarityMetrics]) -> str:
    tolerances = sorted({key for item in metrics for key in item.f1_by_tolerance}, key=float)
    header = [
        "# Похожесть плана на проектное решение",
        "",
        "| объект | прогон | цель | эталон | план | доля | "
        + " | ".join(f"F1 {tolerance} м" for tolerance in tolerances)
        + " | расхождение, м | шаг эталона, м | шаг плана, м | в группах: эталон | в группах: план"
        + " | в рядах: эталон | в рядах: план |",
        "|---|---|---|---|---|---|" + "---|" * len(tolerances) + "---|---|---|---|---|---|---|",
    ]
    rows = [
        f"| {item.object_id} | {item.source} | {item.target} | {item.reference} | {item.planned} | "
        f"{item.count_ratio:.2f} | "
        + " | ".join(f"{item.f1_by_tolerance[tolerance]:.3f}" for tolerance in tolerances)
        + f" | {item.chamfer_m:.1f} | {item.reference_spacing_m:.1f} | {item.planned_spacing_m:.1f} | "
        f"{item.reference_grouped_share:.2f} | {item.planned_grouped_share:.2f} | "
        f"{item.reference_row_share:.2f} | {item.planned_row_share:.2f} |"
        for item in metrics
    ]
    return "\n".join(header + rows) + "\n"
