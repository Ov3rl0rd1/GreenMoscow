import shutil
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from greenplan.api.job_repository import FAILED, QUEUED, RUNNING, SUCCEEDED, JobRecord, JobRepository
from greenplan.api.upload_storage import UploadStorage, is_archive
from greenplan.domain.errors import GreenPlanError, InvalidUploadError, JobNotFoundError
from greenplan.ingest.input_selection import prefer_dxf, unique_paths
from greenplan.pipeline.pipeline_request import PipelineRequest
from greenplan.pipeline.planning_pipeline import PipelineResult, PlanningPipeline
from greenplan.pipeline.run_config import RunConfig, RunConfigLoader, TerritorySettings

INPUT_DIRECTORY = "input"
OUTPUT_DIRECTORY = "output"
CONFIG_FILE_NAME = "config.yaml"

PipelineFactory = Callable[[RunConfig], PlanningPipeline]
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
    ) -> JobRecord:
        if not uploads:
            raise InvalidUploadError("no drawings were uploaded")
        job_id = uuid.uuid4().hex
        directory = self._repository.directory(job_id)
        input_directory = directory / INPUT_DIRECTORY
        input_directory.mkdir(parents=True)
        try:
            stored = self._stored_inputs(input_directory, uploads, main_file)
            self._store_config(directory, config_text)
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
            overlay_files=[relative_name(path, input_directory) for path in stored.overlays],
        )
        self._repository.save(record)
        return record

    def execute(self, job_id: str) -> None:
        record = self._update(self._repository.load(job_id), status=RUNNING)
        directory = self._repository.directory(job_id)
        try:
            result = self._run_pipeline(record, directory)
        except Exception as error:
            self._update(record, status=FAILED, error=f"{type(error).__name__}: {error}")
            return
        self._update(
            record, status=SUCCEEDED, artifacts=sorted(result.artifacts), summary=job_summary(result)
        )

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
        input_directory = directory / INPUT_DIRECTORY
        request = PipelineRequest(
            input_path=input_directory / record.main_file,
            output_directory=directory / OUTPUT_DIRECTORY,
            title=record.title,
            search_root=input_directory,
            generated_at=self._clock(),
            overlay_paths=tuple(input_directory / name for name in record.overlay_files),
        )
        return self._pipeline_factory(config).run(request)

    def _update(self, record: JobRecord, **changes: Any) -> JobRecord:
        updated = replace(record, updated_at=self._clock(), **changes)
        self._repository.save(updated)
        return updated


def relative_name(path: Path, directory: Path) -> str:
    return path.relative_to(directory.resolve()).as_posix()


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
        "timings_s": result.timings_s,
        "peak_memory_mb": result.peak_memory_mb,
    }
