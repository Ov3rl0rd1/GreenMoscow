import shutil
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from greenplan.api.job_repository import FAILED, QUEUED, RUNNING, SUCCEEDED, JobRecord, JobRepository
from greenplan.api.upload_storage import UploadStorage
from greenplan.domain.errors import GreenPlanError, JobNotFoundError
from greenplan.pipeline.pipeline_request import PipelineRequest
from greenplan.pipeline.planning_pipeline import PipelineResult, PlanningPipeline
from greenplan.pipeline.run_config import RunConfig, RunConfigLoader

INPUT_DIRECTORY = "input"
OUTPUT_DIRECTORY = "output"
CONFIG_FILE_NAME = "config.yaml"

PipelineFactory = Callable[[RunConfig], PlanningPipeline]
Clock = Callable[[], str]


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
        self, upload_name: str, content: bytes, title: str, main_file: str | None, config_text: str | None
    ) -> JobRecord:
        job_id = uuid.uuid4().hex
        directory = self._repository.directory(job_id)
        input_directory = directory / INPUT_DIRECTORY
        input_directory.mkdir(parents=True)
        try:
            main = self._stored_main(input_directory, upload_name, content, main_file)
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
            upload_name=upload_name,
            main_file=main.relative_to(input_directory.resolve()).as_posix(),
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

    def _stored_main(
        self, input_directory: Path, upload_name: str, content: bytes, main_file: str | None
    ) -> Path:
        drawings = self._storage.store(input_directory, upload_name, content)
        return self._storage.resolve_main(input_directory, drawings, main_file).resolve()

    def _store_config(self, directory: Path, config_text: str | None) -> None:
        if not config_text:
            return
        path = directory / CONFIG_FILE_NAME
        path.write_text(config_text, encoding="utf-8")
        self._config_loader.load(path)

    def _run_pipeline(self, record: JobRecord, directory: Path) -> PipelineResult:
        config_path = directory / CONFIG_FILE_NAME
        config = self._config_loader.load(config_path if config_path.is_file() else None)
        input_directory = directory / INPUT_DIRECTORY
        request = PipelineRequest(
            input_path=input_directory / record.main_file,
            output_directory=directory / OUTPUT_DIRECTORY,
            title=record.title,
            search_root=input_directory,
            generated_at=self._clock(),
        )
        return self._pipeline_factory(config).run(request)

    def _update(self, record: JobRecord, **changes: Any) -> JobRecord:
        updated = replace(record, updated_at=self._clock(), **changes)
        self._repository.save(updated)
        return updated


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
        "timings_s": result.timings_s,
    }
