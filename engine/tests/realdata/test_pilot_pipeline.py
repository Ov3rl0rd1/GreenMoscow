import json
from pathlib import Path

import pytest

from greenplan.cli.commands import EXIT_OK
from greenplan.cli.main import main
from greenplan.pipeline.run_summary import RUN_SUMMARY_NAME

from fixtures.pilot_objects import BAGRITSKOGO_MAIN

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


def test_cli_run_on_pilot_object_is_verified_and_timed(
    pilot_objects_root: Path, dwg2dxf_path: Path, repository_root: Path, knowledge_root: Path, tmp_path: Path
) -> None:
    arguments = [
        "run",
        "--input",
        str(pilot_objects_root / BAGRITSKOGO_MAIN),
        "--output",
        str(tmp_path),
        "--title",
        "Улица Багрицкого",
        "--knowledge",
        str(knowledge_root),
        "--dwg2dxf",
        str(dwg2dxf_path),
        "--cache",
        str(repository_root / "data" / "cache" / "converted"),
    ]
    assert main(arguments) == EXIT_OK
    summary = json.loads((tmp_path / RUN_SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["verification"]["is_valid"] is True
    assert summary["plants"]["trees"] > 20
    assert summary["total_s"] > 0
