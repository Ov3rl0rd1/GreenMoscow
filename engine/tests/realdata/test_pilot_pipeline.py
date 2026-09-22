import json
from pathlib import Path

import pytest

from greenplan.cli.commands import EXIT_OK
from greenplan.cli.main import main
from greenplan.pipeline.run_summary import RUN_SUMMARY_NAME

from fixtures.pilot_objects import BAGRITSKOGO_MAIN

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]

PLACEMENT_BUDGET_S = 30 * 60
RUN_BUDGET_S = 60 * 60
MEMORY_BUDGET_MB = 8 * 1024
PLACEMENT_STAGES = ("read_drawings", "recognize_site", "place_plants")


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
    assert summary["peak_memory_mb"] > 0
    placement_s = sum(summary["timings_s"][stage] for stage in PLACEMENT_STAGES)
    assert placement_s < PLACEMENT_BUDGET_S, summary["timings_s"]
    assert summary["total_s"] < RUN_BUDGET_S, summary["timings_s"]
    assert summary["peak_memory_mb"] < MEMORY_BUDGET_MB, summary["memory_mb"]
