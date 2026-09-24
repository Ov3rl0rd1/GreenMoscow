from dataclasses import replace
from pathlib import Path

import pytest

from greenplan.api.job_repository import FAILED, RUNNING, SUCCEEDED, JobRepository
from greenplan.api.job_runner import IsolatedJobRunner, crash_message
from greenplan.api.job_service import INTERRUPTED_MESSAGE, JobService, UploadedFile
from greenplan.api.service_factory import ServiceLocation, build_job_service

from fixtures.job_workers import CRASH_EXIT_CODE, crashing_worker


@pytest.fixture
def location(knowledge_root: Path, tmp_path: Path) -> ServiceLocation:
    return ServiceLocation(tmp_path / "jobs", knowledge_root, tmp_path / "cache", None)


def queued_job(service: JobService) -> str:
    return service.create([UploadedFile("Улица 5.dxf", b"0\nEOF\n")], "Улица", None, None).job_id


def test_crashed_worker_leaves_a_failed_job_with_the_reason(location: ServiceLocation) -> None:
    service = build_job_service(location)
    job_id = queued_job(service)
    IsolatedJobRunner(service, location, crashing_worker).run(job_id)
    record = service.get(job_id)
    assert record.status == FAILED
    assert f"кодом {CRASH_EXIT_CODE}" in record.error


@pytest.mark.parametrize("exit_code", [-9, 137])
def test_kill_by_the_system_is_explained_as_lack_of_memory(exit_code: int) -> None:
    assert "не хватило памяти" in crash_message(exit_code)


def test_jobs_left_unfinished_by_a_restart_are_failed(location: ServiceLocation) -> None:
    service = build_job_service(location)
    repository = JobRepository(location.jobs_root)
    queued, running, finished = (queued_job(service) for _ in range(3))
    repository.save(replace(repository.load(running), status=RUNNING))
    repository.save(replace(repository.load(finished), status=SUCCEEDED))
    service.fail_interrupted()
    assert {service.get(job_id).error for job_id in (queued, running)} == {INTERRUPTED_MESSAGE}
    assert service.get(running).status == FAILED
    assert service.get(finished).status == SUCCEEDED
    assert service.get(finished).error is None
