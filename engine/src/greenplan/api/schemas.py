from dataclasses import asdict
from typing import Any

from pydantic import BaseModel

from greenplan.api.job_repository import JobRecord


class JobResponse(BaseModel):
    job_id: str
    status: str
    title: str
    created_at: str
    updated_at: str
    upload_name: str
    main_file: str
    error: str | None
    overlay_files: list[str] = []
    territory: str = ""
    stage: str = ""
    artifacts: list[str]
    summary: dict[str, Any]

    @classmethod
    def from_record(cls, record: JobRecord) -> "JobResponse":
        return cls(**asdict(record))


class HealthResponse(BaseModel):
    status: str
    version: str
    dwg2dxf_available: bool
