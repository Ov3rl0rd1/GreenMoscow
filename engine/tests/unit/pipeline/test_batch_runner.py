import json
from pathlib import Path

import pytest

from greenplan.domain.errors import DrawingLoadError
from greenplan.explain.report_model import ReportSummary
from greenplan.knowledge.pilot_objects import PilotCatalog
from greenplan.pipeline.batch_runner import BATCH_JSON_NAME, BATCH_MARKDOWN_NAME, BatchRunner
from greenplan.pipeline.planning_pipeline import PipelineResult
from greenplan.verify.verification_model import IntegrityReport, VerificationReport

CATALOG_YAML = """
meta: {dataset_root: "data/pilot"}
objects:
  - {id: first, name: "Первая улица", level: A, layer_scheme: pl_prefix,
     input: "1. Первая/Исходные/main.dwg", reference: "1. Первая/Проект/plan.dwg"}
  - {id: second, name: "Вторая улица", level: B, layer_scheme: null,
     input: "2. Вторая/Исходные/main.dwg", reference: "2. Вторая/Проект/plan.dwg"}
"""


def summary() -> ReportSummary:
    return ReportSummary(
        trees=12,
        shrubs=30,
        conditional=2,
        rejected=5,
        species=(),
        plantable_area_m2=1000.0,
        tree_allowed_area_m2=500.0,
        max_trees=20,
        max_shrubs=60,
        tree_spacing_m=6.0,
        shrub_spacing_m=1.0,
        boundary_source="граница работ",
        lawn_source="газоны",
        annotated_network_share=0.5,
        unresolved_references=(),
    )


def verification() -> VerificationReport:
    return VerificationReport(
        output_path="out.dxf",
        plants_checked=42,
        violations=(),
        integrity=IntegrityReport((), (), (), ()),
    )


class FakePipeline:
    def __init__(self, failing: set[str]) -> None:
        self._failing = failing
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        if request.title in self._failing:
            raise DrawingLoadError(f"не открывается {request.input_path.name}")
        return PipelineResult(
            output_dxf=request.output_directory / "result.dxf",
            artifacts={},
            report_summary=summary(),
            verification=verification(),
            timings_s={"read_drawings": 10.0, "place_plants": 5.0},
            diagnostics=None,
            memory_mb={"read_drawings": 900.0},
            peak_memory_mb=1200.0,
        )


@pytest.fixture
def catalog(tmp_path: Path) -> PilotCatalog:
    path = tmp_path / "pilot_objects.yaml"
    path.write_text(CATALOG_YAML, encoding="utf-8")
    return PilotCatalog.from_file(path)


def test_catalog_reads_objects_and_filters(catalog: PilotCatalog) -> None:
    assert [item.object_id for item in catalog.objects] == ["first", "second"]
    assert [item.object_id for item in catalog.of_levels(["A"])] == ["first"]
    assert [item.object_id for item in catalog.selected(None, ["second"])] == ["second"]
    assert catalog.objects[0].object_folder == "1. Первая"


def test_batch_runs_every_object_and_collects_measurements(catalog: PilotCatalog, tmp_path: Path) -> None:
    pipeline = FakePipeline(failing=set())
    outcomes = BatchRunner(pipeline).run(catalog, tmp_path / "data", tmp_path / "out")
    assert [item.object_id for item in outcomes] == ["first", "second"]
    assert all(item.succeeded for item in outcomes)
    assert outcomes[0].trees == 12
    assert outcomes[0].total_s == 15.0
    assert outcomes[0].peak_memory_mb == 1200.0
    assert pipeline.requests[0].search_root == tmp_path / "data" / "1. Первая"


def test_failed_object_does_not_stop_the_batch(catalog: PilotCatalog, tmp_path: Path) -> None:
    outcomes = BatchRunner(FakePipeline(failing={"Первая улица"})).run(
        catalog, tmp_path / "data", tmp_path / "out"
    )
    assert not outcomes[0].succeeded
    assert "не открывается" in outcomes[0].reason
    assert outcomes[1].succeeded


def test_batch_report_is_written_in_json_and_markdown(catalog: PilotCatalog, tmp_path: Path) -> None:
    output = tmp_path / "out"
    BatchRunner(FakePipeline(failing={"Вторая улица"})).run(catalog, tmp_path / "data", output)
    payload = json.loads((output / BATCH_JSON_NAME).read_text(encoding="utf-8"))
    text = (output / BATCH_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert [item["object_id"] for item in payload] == ["first", "second"]
    assert "Пакетный прогон объектов" in text
    assert "## Не прошли" in text
    assert "second" in text
