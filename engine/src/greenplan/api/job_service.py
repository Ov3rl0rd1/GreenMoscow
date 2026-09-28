import shutil
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

from greenplan.api.job_repository import FAILED, QUEUED, RUNNING, SUCCEEDED, JobRecord, JobRepository
from greenplan.api.upload_storage import UploadStorage, is_archive
from greenplan.domain.errors import GreenPlanError, InvalidUploadError, JobNotFoundError
from greenplan.ingest.input_selection import prefer_dxf, unique_paths
from greenplan.pipeline.pipeline_request import PipelineRequest
from greenplan.pipeline.planning_pipeline import PipelineResult, PlanningPipeline
from greenplan.pipeline.run_config import RunConfig, RunConfigLoader, TerritorySettings, merged_config_text

INPUT_DIRECTORY = "input"
OUTPUT_DIRECTORY = "output"
CONFIG_FILE_NAME = "config.yaml"
UNFINISHED_STATUSES = frozenset({QUEUED, RUNNING})
INTERRUPTED_MESSAGE = "Расчёт прерван перезапуском сервиса. Запустите задачу заново."
MODEL_GUIDANCE_CHOICE = "model"
RULES_GUIDANCE_CHOICE = "rules"
GUIDANCE_CHOICES = frozenset({MODEL_GUIDANCE_CHOICE, RULES_GUIDANCE_CHOICE})

PipelineFactory = Callable[[RunConfig, bool], PlanningPipeline]
Clock = Callable[[], str]


@dataclass(frozen=True, slots=True)
class UploadedFile:
    name: str
    content: bytes


@dataclass(frozen=True, slots=True)
class StoredInputs:
    main: Path
    overlays: tuple[Path, ...]


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        storage: UploadStorage,
        pipeline_factory: PipelineFactory,
        config_loader: RunConfigLoader,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._pipeline_factory = pipeline_factory
        self._config_loader = config_loader
        self._clock = clock

    def create(
        self,
        uploads: Sequence[UploadedFile],
        title: str,
        main_file: str | None,
        config_text: str | None,
        territory: str | None = None,
        guidance: str | None = None,
        exceed_density: bool = False,
        settings: Mapping[str, Any] | None = None,
    ) -> JobRecord:
        if guidance and guidance not in GUIDANCE_CHOICES:
            raise InvalidUploadError(f"unknown guidance '{guidance}': expected model or rules")
        if not uploads:
            raise InvalidUploadError("no drawings were uploaded")
        job_id = uuid.uuid4().hex
        directory = self._repository.directory(job_id)
        input_directory = directory / INPUT_DIRECTORY
        input_directory.mkdir(parents=True)
        try:
            stored = self._stored_inputs(input_directory, uploads, main_file)
            self._store_config(
                directory, merged_config_text(config_text, settings) if settings else config_text
            )
        except GreenPlanError:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        now = self._clock()
        record = JobRecord(
            job_id=job_id,
            status=QUEUED,
            title=title,
            created_at=now,
            updated_at=now,
            upload_name=", ".join(upload.name for upload in uploads),
            main_file=relative_name(stored.main, input_directory),
            territory=territory or "",
            guidance=guidance or MODEL_GUIDANCE_CHOICE,
            exceed_density=exceed_density,
            overlay_files=[relative_name(path, input_directory) for path in stored.overlays],
        )
        self._repository.save(record)
        return record

    def execute(self, job_id: str) -> None:
        record = self._update(self._repository.load(job_id), status=RUNNING, started_at=self._clock())
        directory = self._repository.directory(job_id)
        try:
            result = self._run_pipeline(record, directory)
        except Exception as error:
            self._change(
                job_id, status=FAILED, error=f"{type(error).__name__}: {error}", finished_at=self._clock()
            )
            return
        self._change(
            job_id,
            status=SUCCEEDED,
            stage="",
            stage_started_at="",
            finished_at=self._clock(),
            stage_timings=dict(result.timings_s),
            artifacts=sorted(result.artifacts),
            summary=job_summary(result),
        )

    def fail_unfinished(self, job_id: str, message: str) -> None:
        record = self._repository.load(job_id)
        if record.status in UNFINISHED_STATUSES:
            self._update(record, status=FAILED, error=message, finished_at=self._clock())

    def fail_interrupted(self) -> None:
        for record in self._repository.all():
            self.fail_unfinished(record.job_id, INTERRUPTED_MESSAGE)

    def get(self, job_id: str) -> JobRecord:
        return self._repository.load(job_id)

    def all(self) -> list[JobRecord]:
        return self._repository.all()

    def artifact(self, job_id: str, name: str) -> Path:
        record = self._repository.load(job_id)
        if name not in record.artifacts:
            raise JobNotFoundError(f"artifact not found: {name}")
        return self._repository.directory(job_id) / OUTPUT_DIRECTORY / name

    def _stored_inputs(
        self, input_directory: Path, uploads: Sequence[UploadedFile], main_file: str | None
    ) -> StoredInputs:
        drawings: list[Path] = []
        direct: list[Path] = []
        for upload in uploads:
            stored = self._storage.store(input_directory, upload.name, upload.content)
            drawings.extend(stored)
            if not is_archive(upload.name):
                direct.extend(stored)
        main = self._storage.resolve_main(input_directory, unique_paths(drawings), main_file).resolve()
        overlays = tuple(
            path.resolve() for path in prefer_dxf(unique_paths(direct)) if path.resolve() != main
        )
        return StoredInputs(main, overlays)

    def _store_config(self, directory: Path, config_text: str | None) -> None:
        if not config_text:
            return
        path = directory / CONFIG_FILE_NAME
        path.write_text(config_text, encoding="utf-8")
        self._config_loader.load(path)

    def _run_pipeline(self, record: JobRecord, directory: Path) -> PipelineResult:
        config_path = directory / CONFIG_FILE_NAME
        config = self._config_loader.load(config_path if config_path.is_file() else None)
        if record.territory:
            config = replace(config, territory=TerritorySettings(record.territory))
        if record.exceed_density:
            config = replace(config, placement=replace(config.placement, respect_density_cap=False))
        input_directory = directory / INPUT_DIRECTORY
        request = PipelineRequest(
            input_path=input_directory / record.main_file,
            output_directory=directory / OUTPUT_DIRECTORY,
            title=record.title,
            search_root=input_directory,
            generated_at=self._clock(),
            overlay_paths=tuple(input_directory / name for name in record.overlay_files),
        )
        pipeline = self._pipeline_factory(config, record.guidance != RULES_GUIDANCE_CHOICE)
        return pipeline.run(request, partial(self._report_stage, record.job_id))

    def _report_stage(self, job_id: str, stage: str, finished: Mapping[str, float]) -> None:
        self._change(job_id, stage=stage, stage_started_at=self._clock(), stage_timings=dict(finished))

    def _change(self, job_id: str, **changes: Any) -> JobRecord:
        return self._update(self._repository.load(job_id), **changes)

    def _update(self, record: JobRecord, **changes: Any) -> JobRecord:
        updated = replace(record, updated_at=self._clock(), **changes)
        self._repository.save(updated)
        return updated


def relative_name(path: Path, directory: Path) -> str:
    return path.relative_to(directory.resolve()).as_posix()


def benefit_summary(result: PipelineResult) -> dict[str, Any]:
    metrics = result.metrics
    if metrics is None:
        return {}
    return {
        "street_front_share": metrics.street_front_share,
        "sidewalk_shade_share": metrics.sidewalk_shade_share,
        "open_lawn_share": metrics.open_lawn_share,
        "crown_share_of_plantable": metrics.crown_share_of_plantable,
        "species_count": metrics.species_count,
        "max_species_share": metrics.max_species_share,
        "elements": dict(metrics.elements),
        "rows_with_hedge": metrics.rows_with_hedge,
    }


def job_summary(result: PipelineResult) -> dict[str, Any]:
    summary = result.report_summary
    return {
        "trees": summary.trees,
        "shrubs": summary.shrubs,
        "conditional": summary.conditional,
        "rejected": summary.rejected,
        "verification_valid": result.verification.is_valid,
        "violations": len(result.verification.violations),
        "integrity_is_intact": result.verification.integrity.is_intact,
        "warnings": list(summary.warnings),
        "guidance": summary.guidance_source,
        "expected_trees": summary.expected_trees,
        "expected_shrubs": summary.expected_shrubs,
        "benefits": benefit_summary(result),
        "journal": list(summary.journal),
        "timings_s": result.timings_s,
        "peak_memory_mb": result.peak_memory_mb,
    }
