import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from greenplan.api.app import create_app_from_environment
from greenplan.api.job_repository import FAILED, SUCCEEDED
from greenplan.domain.norms import VERIFIED_STATUSES
from greenplan.explain.report_writers import JSON_REPORT_NAME

from fixtures.drawing_factory import add_line, create_document, save_document
from fixtures.export_pipeline import source_drawing

JOBS = "/api/v1/jobs"


@pytest.fixture(scope="module")
def client(knowledge_root: Path, tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    jobs_root = tmp_path_factory.mktemp("jobs")
    app = create_app_from_environment(
        jobs_root=jobs_root, knowledge=knowledge_root, cache=jobs_root / "cache"
    )
    return TestClient(app)


@pytest.fixture(scope="module")
def drawing_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return source_drawing(tmp_path_factory.mktemp("upload") / "street.dxf").read_bytes()


def submit(client: TestClient, files: dict, data: dict | None = None):
    return client.post(JOBS, files=files, data=data or {})


def test_health_reports_version(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["version"]


def test_norms_endpoint_hides_locators_of_unverified_citations(client: TestClient) -> None:
    rules = client.get("/api/v1/norms").json()["rules"]
    sources = [source for rule in rules for source in rule["sources"]]
    assert len(rules) > 40
    assert all(
        source["locator"] is None for source in sources if source["verification"] not in VERIFIED_STATUSES
    )


def test_swagger_documents_job_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {JOBS, JOBS + "/{job_id}", JOBS + "/{job_id}/artifacts/{name}", "/api/v1/norms"} <= set(paths)


def test_dxf_job_runs_to_completion_and_serves_artifacts(client: TestClient, drawing_bytes: bytes) -> None:
    created = submit(client, {"drawing": ("street.dxf", drawing_bytes)}, {"title": "Улица"})
    assert created.status_code == 202
    job = client.get(f"{JOBS}/{created.json()['job_id']}").json()
    assert job["status"] == SUCCEEDED, job["error"]
    assert job["summary"]["verification_valid"] is True
    assert {JSON_REPORT_NAME, "street_greenplan.dxf", "preview.png"} <= set(job["artifacts"])
    report = client.get(f"{JOBS}/{job['job_id']}/artifacts/{JSON_REPORT_NAME}")
    assert json.loads(report.content)["title"] == "Улица"
    assert client.get(f"{JOBS}/{job['job_id']}/artifacts/job.json").status_code == 404


def zipped(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_zip_upload_requires_main_file_when_several_drawings(
    client: TestClient, drawing_bytes: bytes, tmp_path: Path
) -> None:
    extra = create_document()
    add_line(extra, "Борт", (0, 0), (1, 0))
    extra_bytes = save_document(extra, tmp_path / "extra.dxf").read_bytes()
    archive = zipped({"объект/главный.dxf": drawing_bytes, "объект/ссылки/борт.dxf": extra_bytes})
    rejected = submit(client, {"drawing": ("объект.zip", archive)})
    accepted = submit(client, {"drawing": ("объект.zip", archive)}, {"main_file": "объект/главный.dxf"})
    assert rejected.status_code == 400
    assert accepted.status_code == 202
    assert client.get(f"{JOBS}/{accepted.json()['job_id']}").json()["status"] == SUCCEEDED


@pytest.mark.parametrize(
    ("files", "data"),
    [
        ({"drawing": ("notes.txt", b"text")}, {}),
        ({"drawing": ("evil.zip", zipped({"../escape.dxf": b"0"}))}, {}),
        ({"drawing": ("street.dxf", b"0"), "config": ("config.yaml", b"placement:\n  unknown: 1\n")}, {}),
    ],
)
def test_invalid_uploads_are_rejected(client: TestClient, files: dict, data: dict) -> None:
    assert submit(client, files, data).status_code == 400


def test_broken_drawing_makes_job_fail_with_message(client: TestClient) -> None:
    created = submit(client, {"drawing": ("broken.dxf", b"not a dxf")})
    job = client.get(f"{JOBS}/{created.json()['job_id']}").json()
    assert job["status"] == FAILED
    assert job["error"]


def test_unknown_job_is_not_found(client: TestClient) -> None:
    assert client.get(f"{JOBS}/{'0' * 32}").status_code == 404
    assert client.get(f"{JOBS}/not-a-job").status_code == 404
