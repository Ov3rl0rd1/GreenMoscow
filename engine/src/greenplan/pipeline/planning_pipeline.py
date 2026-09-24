import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from greenplan.domain.drawing import DrawingSet
from greenplan.domain.site import SiteDiagnostics, SiteModel
from greenplan.explain.report_model import ReportSummary
from greenplan.pipeline.components import PipelineComponents
from greenplan.pipeline.environment import current_timestamp
from greenplan.pipeline.pipeline_request import PipelineRequest
from greenplan.pipeline.run_config import RunConfig
from greenplan.pipeline.run_summary import RunSummary
from greenplan.pipeline.stage_timer import StageListener, StageTimer, ignore_stage
from greenplan.verify.verification_model import VerificationReport
from greenplan.verify.verification_writers import write_verification_json, write_verification_markdown

OUTPUT_DXF_SUFFIX = "_greenplan.dxf"
PREVIEW_NAME = "preview.png"
UNSAFE_NAME_CHARACTERS = re.compile(r"[^\w\-.]+")
READ_STAGE = "read_drawings"
RECOGNIZE_STAGE = "recognize_site"
PLACE_STAGE = "place_plants"
SPECIES_STAGE = "select_species"
EXPLAIN_STAGE = "explain"
EXPORT_STAGE = "export_dxf"
VERIFY_STAGE = "verify"


@dataclass(frozen=True)
class RecognizedSite:
    drawing_set: DrawingSet
    site: SiteModel
    source_dxf: Path


@dataclass(frozen=True)
class PipelineResult:
    output_dxf: Path
    artifacts: dict[str, Path]
    report_summary: ReportSummary
    verification: VerificationReport
    timings_s: dict[str, float]
    diagnostics: SiteDiagnostics
    memory_mb: dict[str, float] = field(default_factory=dict)
    peak_memory_mb: float = 0.0


class PlanningPipeline:
    def __init__(self, components: PipelineComponents, config: RunConfig) -> None:
        self._components = components
        self._config = config

    def recognize(
        self,
        input_path: Path,
        search_root: Path | None,
        timer: StageTimer | None = None,
        overlays: Sequence[Path] = (),
    ) -> RecognizedSite:
        stages = timer or StageTimer()
        components = self._components
        with stages.stage(READ_STAGE):
            drawing_set = components.drawing_set_builder.build(input_path, search_root, overlays)
            content = components.content_reader.read(drawing_set)
        with stages.stage(RECOGNIZE_STAGE):
            site = components.site_builder.build(content, drawing_set.unresolved_references)
        return RecognizedSite(drawing_set, site, components.opener.resolve_dxf_path(input_path))

    def verify_output(self, recognized: RecognizedSite, output_dxf: Path) -> VerificationReport:
        return self._components.verifier.verify(recognized.source_dxf, output_dxf, recognized.site)

    def run(self, request: PipelineRequest, on_stage: StageListener = ignore_stage) -> PipelineResult:
        components = self._components
        timer = StageTimer(on_stage)
        generated_at = request.generated_at or current_timestamp()
        directory = request.output_directory
        directory.mkdir(parents=True, exist_ok=True)
        recognized = self.recognize(request.input_path, request.search_root, timer, request.overlay_paths)
        site = recognized.site
        with timer.stage(PLACE_STAGE):
            plan = components.composer.compose(site)
        with timer.stage(SPECIES_STAGE):
            species = components.species_factory.for_site(site).assign(plan.trees + plan.shrubs)
        with timer.stage(EXPLAIN_STAGE):
            report = components.report_builder.build(request.title, site, plan, species)
            artifacts = dict(components.report_writers.write_all(report, directory))
        output_dxf = directory / output_dxf_name(request.input_path)
        with timer.stage(EXPORT_STAGE):
            components.exporter.export(recognized.source_dxf, output_dxf, site, plan, report, generated_at)
            preview = components.preview_renderer.render(
                site, plan.tree_zones, report, directory / PREVIEW_NAME
            )
        with timer.stage(VERIFY_STAGE):
            verification = self.verify_output(recognized, output_dxf)
        for path in (output_dxf, preview, *verification_artifacts(verification, directory)):
            artifacts[path.name] = path
        summary = RunSummary(
            request,
            self._config,
            report.summary,
            verification,
            timer.durations,
            site.diagnostics,
            output_dxf,
            generated_at,
            report.engine_version,
            timer.memory_mb,
            timer.peak_memory_mb,
        ).write(directory)
        artifacts[summary.name] = summary
        return PipelineResult(
            output_dxf,
            artifacts,
            report.summary,
            verification,
            timer.durations,
            site.diagnostics,
            timer.memory_mb,
            timer.peak_memory_mb,
        )


def output_dxf_name(input_path: Path) -> str:
    return f"{UNSAFE_NAME_CHARACTERS.sub('_', input_path.stem)}{OUTPUT_DXF_SUFFIX}"


def verification_artifacts(report: VerificationReport, directory: Path) -> tuple[Path, Path]:
    return write_verification_json(report, directory), write_verification_markdown(report, directory)
