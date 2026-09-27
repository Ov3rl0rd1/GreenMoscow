import json
from pathlib import Path

import pytest

from greenplan.cli.commands import EXIT_ERROR, EXIT_OK
from greenplan.cli.main import main
from greenplan.explain.report_writers import CSV_REPORT_NAME, JSON_REPORT_NAME, MARKDOWN_REPORT_NAME
from greenplan.pipeline.planning_pipeline import PREVIEW_NAME
from greenplan.pipeline.run_summary import RUN_SUMMARY_NAME
from greenplan.verify.verification_writers import JSON_VERIFICATION_NAME, MARKDOWN_VERIFICATION_NAME

from fixtures.export_pipeline import source_drawing

EXPECTED_ARTIFACTS = (
    JSON_REPORT_NAME,
    CSV_REPORT_NAME,
    MARKDOWN_REPORT_NAME,
    PREVIEW_NAME,
    JSON_VERIFICATION_NAME,
    MARKDOWN_VERIFICATION_NAME,
    RUN_SUMMARY_NAME,
    "street_greenplan.dxf",
)


@pytest.fixture(scope="module")
def workspace(knowledge_root: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("cli")
    source = source_drawing(directory / "street.dxf")
    output = directory / "out"
    code = main(["run", "--input", str(source), "--output", str(output), "--knowledge", str(knowledge_root)])
    return {"source": source, "output": output, "code": code, "knowledge": knowledge_root}


def test_run_command_produces_all_artifacts(workspace: dict) -> None:
    assert workspace["code"] == EXIT_OK
    assert all((workspace["output"] / name).is_file() for name in EXPECTED_ARTIFACTS)


def test_run_summary_records_counts_timings_and_verification(workspace: dict) -> None:
    summary = json.loads((workspace["output"] / RUN_SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["plants"]["trees"] > 0
    assert summary["verification"] == {"is_valid": True, "violations": 0, "integrity_is_intact": True}
    assert set(summary["timings_s"]) >= {"read_drawings", "place_plants", "export_dxf", "verify"}
    assert summary["site"]["boundary_source"] == "work_boundary"


def test_verify_command_confirms_generated_dxf(workspace: dict, tmp_path: Path) -> None:
    arguments = [
        "verify",
        "--input",
        str(workspace["source"]),
        "--dxf",
        str(workspace["output"] / "street_greenplan.dxf"),
        "--report-dir",
        str(tmp_path),
        "--knowledge",
        str(workspace["knowledge"]),
    ]
    assert main(arguments) == EXIT_OK
    assert (tmp_path / JSON_VERIFICATION_NAME).is_file()


def test_inspect_command_prints_recognized_site(workspace: dict, capsys: pytest.CaptureFixture) -> None:
    capsys.readouterr()
    code = main(["inspect", "--input", str(workspace["source"]), "--knowledge", str(workspace["knowledge"])])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["plantable_area_m2"] == pytest.approx(1000.0)
    assert payload["diagnostics"]["obstacle_counts"]["gas_pipeline"] == 1


def test_domain_errors_become_exit_code_one(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    code = main(["inspect", "--input", str(tmp_path / "missing.dxf"), "--knowledge", str(tmp_path)])
    assert code == EXIT_ERROR
    assert "Ошибка" in capsys.readouterr().err


def test_second_run_takes_the_recognised_site_from_the_cache(knowledge_root: Path, tmp_path: Path) -> None:
    source = source_drawing(tmp_path / "street.dxf")
    cache = tmp_path / "cache"
    arguments = ["run", "--input", str(source), "--knowledge", str(knowledge_root), "--cache", str(cache)]
    assert main([*arguments, "--output", str(tmp_path / "first")]) == EXIT_OK
    stored = list((cache / "sites").glob("*.site.pkl"))
    assert len(stored) == 1
    assert main([*arguments, "--output", str(tmp_path / "second")]) == EXIT_OK
    first = json.loads((tmp_path / "first" / RUN_SUMMARY_NAME).read_text(encoding="utf-8"))
    second = json.loads((tmp_path / "second" / RUN_SUMMARY_NAME).read_text(encoding="utf-8"))
    assert second["plants"] == first["plants"]
    assert second["verification"] == first["verification"]
    assert list((cache / "sites").glob("*.site.pkl")) == stored
