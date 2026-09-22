import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from greenplan.knowledge.pilot_objects import PilotCatalog, PilotObject
from greenplan.pipeline.pipeline_request import PipelineRequest
from greenplan.pipeline.planning_pipeline import PipelineResult, PlanningPipeline

BATCH_JSON_NAME = "batch_report.json"
BATCH_MARKDOWN_NAME = "batch_report.md"
TIMING_DECIMALS = 3
ProgressReport = Callable[["BatchOutcome"], None]


@dataclass(frozen=True, slots=True)
class BatchOutcome:
    object_id: str
    level: str
    succeeded: bool
    reason: str = ""
    trees: int = 0
    shrubs: int = 0
    conditional: int = 0
    rejected: int = 0
    violations: int = 0
    integrity_is_intact: bool = False
    total_s: float = 0.0
    peak_memory_mb: float = 0.0


class BatchRunner:
    def __init__(self, pipeline: PlanningPipeline) -> None:
        self._pipeline = pipeline

    def run(
        self,
        catalog: PilotCatalog,
        dataset_root: Path,
        output_root: Path,
        levels: Sequence[str] | None = None,
        object_ids: Sequence[str] | None = None,
        on_result: ProgressReport | None = None,
    ) -> list[BatchOutcome]:
        outcomes: list[BatchOutcome] = []
        for item in catalog.selected(levels, object_ids):
            outcome = self.run_object(item, dataset_root, output_root)
            outcomes.append(outcome)
            if on_result is not None:
                on_result(outcome)
        write_batch_report(output_root, outcomes)
        return outcomes

    def run_object(self, item: PilotObject, dataset_root: Path, output_root: Path) -> BatchOutcome:
        request = PipelineRequest(
            input_path=dataset_root / item.input_path,
            output_directory=output_root / item.object_id,
            title=item.name,
            search_root=dataset_root / item.object_folder,
        )
        try:
            return _succeeded(item, self._pipeline.run(request))
        except Exception as error:
            return BatchOutcome(item.object_id, item.level, False, f"{type(error).__name__}: {error}")


def _succeeded(item: PilotObject, result: PipelineResult) -> BatchOutcome:
    summary = result.report_summary
    return BatchOutcome(
        object_id=item.object_id,
        level=item.level,
        succeeded=True,
        trees=summary.trees,
        shrubs=summary.shrubs,
        conditional=summary.conditional,
        rejected=summary.rejected,
        violations=len(result.verification.violations),
        integrity_is_intact=result.verification.integrity.is_intact,
        total_s=round(sum(result.timings_s.values()), TIMING_DECIMALS),
        peak_memory_mb=result.peak_memory_mb,
    )


def write_batch_report(output_root: Path, outcomes: Sequence[BatchOutcome]) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / BATCH_JSON_NAME
    json_path.write_text(
        json.dumps([asdict(item) for item in outcomes], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_path = output_root / BATCH_MARKDOWN_NAME
    markdown_path.write_text(render_batch_markdown(outcomes), encoding="utf-8")
    return json_path, markdown_path


def render_batch_markdown(outcomes: Sequence[BatchOutcome]) -> str:
    lines = [
        "# Пакетный прогон объектов",
        "",
        "| Объект | Уровень | Деревья | Кустарники | Условно | Отказы | Нарушения | Время, с | Память, МБ |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in outcomes:
        if not item.succeeded:
            lines.append(f"| {item.object_id} | {item.level} | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {item.object_id} | {item.level} | {item.trees} | {item.shrubs} | {item.conditional} | "
            f"{item.rejected} | {item.violations} | {item.total_s} | {item.peak_memory_mb} |"
        )
    failed = [item for item in outcomes if not item.succeeded]
    if failed:
        lines.extend(["", "## Не прошли", "", *(f"- {item.object_id}: {item.reason}" for item in failed)])
    return "\n".join(lines) + "\n"
