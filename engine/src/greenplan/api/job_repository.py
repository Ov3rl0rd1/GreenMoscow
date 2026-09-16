import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from greenplan.domain.errors import JobNotFoundError

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
JOB_FILE_NAME = "job.json"
JOB_IDENTIFIER_PATTERN = re.compile(r"^[0-9a-f]{32}$")
TEMPORARY_SUFFIX = ".tmp"


@dataclass
class JobRecord:
    job_id: str
    status: str
    title: str
    created_at: str
    updated_at: str
    upload_name: str
    main_file: str
    error: str | None = None
    overlay_files: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class JobRepository:
    def __init__(self, jobs_root: Path) -> None:
        self._jobs_root = jobs_root

    def directory(self, job_id: str) -> Path:
        if not JOB_IDENTIFIER_PATTERN.match(job_id):
            raise JobNotFoundError(f"job not found: {job_id}")
        return self._jobs_root / job_id

    def save(self, record: JobRecord) -> None:
        directory = self.directory(record.job_id)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f"{JOB_FILE_NAME}{TEMPORARY_SUFFIX}"
        temporary.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(directory / JOB_FILE_NAME)

    def load(self, job_id: str) -> JobRecord:
        path = self.directory(job_id) / JOB_FILE_NAME
        if not path.is_file():
            raise JobNotFoundError(f"job not found: {job_id}")
        return JobRecord(**json.loads(path.read_text(encoding="utf-8")))

    def all(self) -> list[JobRecord]:
        if not self._jobs_root.is_dir():
            return []
        paths = sorted(self._jobs_root.glob(f"*/{JOB_FILE_NAME}"))
        records = [
            self.load(path.parent.name) for path in paths if JOB_IDENTIFIER_PATTERN.match(path.parent.name)
        ]
        return sorted(records, key=lambda record: record.created_at, reverse=True)
