import json
from pathlib import Path

import pytest

from greenplan.knowledge.pilot_objects import PilotCatalog
from greenplan.pipeline.batch_runner import (
    BATCH_JSON_NAME,
    BATCH_MARKDOWN_NAME,
    BatchRunner,
    ParallelBatchRunner,
)

from fixtures.batch_workers import FakePipeline, crashing_pipeline, fake_pipeline

CATALOG_YAML = """
meta: {dataset_root: "data/pilot"}
objects:
  - {id: first, name: "Первая улица", level: A, layer_scheme: pl_prefix,
     input: "1. Первая/Исходные/main.dwg", reference: "1. Первая/Проект/plan.dwg"}
  - {id: second, name: "Вторая улица", level: B, layer_scheme: null,
     input: "2. Вторая/Исходные/main.dwg", reference: "2. Вторая/Проект/plan.dwg"}
"""


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


def test_progress_is_reported_object_by_object(catalog: PilotCatalog, tmp_path: Path) -> None:
    seen = []
    BatchRunner(FakePipeline(failing={"Вторая улица"})).run(
        catalog, tmp_path / "data", tmp_path / "out", on_result=seen.append
    )
    assert [item.object_id for item in seen] == ["first", "second"]
    assert seen[0].succeeded and not seen[1].succeeded


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


class BrokenPipeline(FakePipeline):
    def run(self, request):
        if request.title == "Первая улица":
            raise UnicodeEncodeError("utf-8", "\udcd1", 0, 1, "surrogates not allowed")
        return super().run(request)


def test_unexpected_error_is_recorded_and_the_batch_continues(catalog: PilotCatalog, tmp_path: Path) -> None:
    outcomes = BatchRunner(BrokenPipeline(failing=set())).run(catalog, tmp_path / "data", tmp_path / "out")
    assert not outcomes[0].succeeded
    assert "UnicodeEncodeError" in outcomes[0].reason
    assert outcomes[1].succeeded


def test_batch_markdown_shows_source_integrity(catalog: PilotCatalog, tmp_path: Path) -> None:
    output = tmp_path / "out"
    BatchRunner(FakePipeline(failing=set())).run(catalog, tmp_path / "data", output)
    text = (output / BATCH_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "Исходник цел" in text
    assert "| да |" in text


def test_parallel_batch_keeps_catalog_order_and_reports_every_object(
    catalog: PilotCatalog, tmp_path: Path
) -> None:
    seen = []
    output = tmp_path / "out"
    outcomes = ParallelBatchRunner(fake_pipeline, 2).run(
        catalog, tmp_path / "data", output, on_result=seen.append
    )
    assert [item.object_id for item in outcomes] == ["first", "second"]
    assert outcomes[0].succeeded and outcomes[0].trees == 12
    assert not outcomes[1].succeeded and "не открывается" in outcomes[1].reason
    assert sorted(item.object_id for item in seen) == ["first", "second"]
    payload = json.loads((output / BATCH_JSON_NAME).read_text(encoding="utf-8"))
    assert [item["object_id"] for item in payload] == ["first", "second"]


def test_crashed_worker_is_recorded_as_a_failed_object(catalog: PilotCatalog, tmp_path: Path) -> None:
    outcomes = ParallelBatchRunner(crashing_pipeline, 2).run(
        catalog, tmp_path / "data", tmp_path / "out", object_ids=["first"]
    )
    assert [item.object_id for item in outcomes] == ["first"]
    assert not outcomes[0].succeeded
    assert "BrokenProcessPool" in outcomes[0].reason
