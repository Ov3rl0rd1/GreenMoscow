import base64
import io
import json
import urllib.parse
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
CRLF = "\r\n"


@pytest.fixture(scope="module")
def client(knowledge_root: Path, tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    jobs_root = tmp_path_factory.mktemp("jobs")
    app = create_app_from_environment(
        jobs_root=jobs_root, knowledge=knowledge_root, cache=jobs_root / "cache", isolated=False
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
    assert any("особо охраняемые" in warning for warning in job["summary"]["warnings"])
    assert {JSON_REPORT_NAME, "street_greenplan.dxf", "preview.png"} <= set(job["artifacts"])
    report = client.get(f"{JOBS}/{job['job_id']}/artifacts/{JSON_REPORT_NAME}")
    assert json.loads(report.content)["title"] == "Улица"
    assert client.get(f"{JOBS}/{job['job_id']}/artifacts/job.json").status_code == 404


def test_territory_categories_are_listed(client: TestClient) -> None:
    items = client.get("/api/v1/territories").json()
    assert {"district_street", "residential_yard", "park"} <= {item["id"] for item in items}
    assert all(item["name_ru"] and item["composition_ru"] for item in items)


def test_job_accepts_a_territory_category(client: TestClient, drawing_bytes: bytes) -> None:
    created = submit(
        client,
        {"drawing": ("street.dxf", drawing_bytes)},
        {"title": "Двор", "territory": "residential_yard"},
    )
    assert created.json()["territory"] == "residential_yard"
    job = client.get(f"{JOBS}/{created.json()['job_id']}").json()
    assert job["status"] == SUCCEEDED, job["error"]


def test_unknown_territory_makes_the_job_fail_with_a_message(
    client: TestClient, drawing_bytes: bytes
) -> None:
    created = submit(
        client, {"drawing": ("street.dxf", drawing_bytes)}, {"title": "Двор", "territory": "подъезд"}
    )
    job = client.get(f"{JOBS}/{created.json()['job_id']}").json()
    assert job["status"] == FAILED
    assert "подъезд" in job["error"]


def zipped(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_zip_upload_picks_the_main_drawing_or_takes_the_given_one(
    client: TestClient, drawing_bytes: bytes, tmp_path: Path
) -> None:
    extra = create_document()
    add_line(extra, "Борт", (0, 0), (1, 0))
    extra_bytes = save_document(extra, tmp_path / "extra.dxf").read_bytes()
    archive = zipped({"объект/главный.dxf": drawing_bytes, "объект/ссылки/борт.dxf": extra_bytes})
    guessed = submit(client, {"drawing": ("объект.zip", archive)})
    given = submit(client, {"drawing": ("объект.zip", archive)}, {"main_file": "объект/ссылки/борт.dxf"})
    assert guessed.status_code == 202
    assert guessed.json()["main_file"] == "объект/главный.dxf"
    assert guessed.json()["overlay_files"] == []
    assert given.json()["main_file"] == "объект/ссылки/борт.dxf"
    assert client.get(f"{JOBS}/{guessed.json()['job_id']}").json()["status"] == SUCCEEDED


def dotnet_multipart(file_name: str, content: bytes) -> tuple[bytes, dict[str, str]]:
    boundary = "dotnet-boundary"
    encoded = base64.b64encode(file_name.encode("utf-8")).decode("ascii")
    disposition = (
        f'form-data; name=drawing; filename="=?utf-8?B?{encoded}?="; '
        f"filename*=utf-8''{urllib.parse.quote(file_name)}"
    )
    lines = [f"--{boundary}", f"Content-Disposition: {disposition}", "Content-Type: application/octet-stream"]
    head = CRLF.join([*lines, "", ""]).encode("ascii")
    tail = f"{CRLF}--{boundary}--{CRLF}".encode("ascii")
    return head + content + tail, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def test_cyrillic_archive_name_with_spaces_sent_by_the_web_client_is_accepted(
    client: TestClient, drawing_bytes: bytes
) -> None:
    archive = zipped({"Объект 5/ГП и ПБ ул Багрицкого.dxf": drawing_bytes})
    body, headers = dotnet_multipart("5. Багрицкого улица.zip", archive)
    created = client.post(JOBS, content=body, headers=headers)
    assert created.status_code == 202, created.text
    assert created.json()["upload_name"] == "5. Багрицкого улица.zip"
    assert created.json()["main_file"] == "Объект 5/ГП и ПБ ул Багрицкого.dxf"
    job = client.get(f"{JOBS}/{created.json()['job_id']}").json()
    assert job["status"] == SUCCEEDED, job["error"]


def test_isolated_worker_runs_the_job_outside_the_api_process(
    knowledge_root: Path, drawing_bytes: bytes, tmp_path: Path
) -> None:
    app = create_app_from_environment(jobs_root=tmp_path, knowledge=knowledge_root, cache=tmp_path / "cache")
    isolated = TestClient(app)
    created = submit(isolated, {"drawing": ("Улица с пробелами.dxf", drawing_bytes)})
    job = isolated.get(f"{JOBS}/{created.json()['job_id']}").json()
    assert job["status"] == SUCCEEDED, job["error"]
    assert job["stage"] == ""
    assert "Улица_с_пробелами_greenplan.dxf" in job["artifacts"]


def test_separate_general_plan_and_base_drawing_run_as_one_site(
    client: TestClient, drawing_bytes: bytes, tmp_path: Path
) -> None:
    base = create_document()
    add_line(base, "Водопровод", (-10, 12), (110, 12))
    base_bytes = save_document(base, tmp_path / "base.dxf").read_bytes()
    files = [
        ("drawing", ("Геоподоснова.dxf", base_bytes)),
        ("drawing", ("Генплан.dxf", drawing_bytes)),
    ]
    created = client.post(JOBS, files=files, data={"title": "Два файла"})
    assert created.status_code == 202
    assert created.json()["main_file"] == "Генплан.dxf"
    assert created.json()["overlay_files"] == ["Геоподоснова.dxf"]
    job = client.get(f"{JOBS}/{created.json()['job_id']}").json()
    assert job["status"] == SUCCEEDED, job["error"]
    assert job["summary"]["verification_valid"] is True


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
