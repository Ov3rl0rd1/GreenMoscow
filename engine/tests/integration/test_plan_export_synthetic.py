import re
from pathlib import Path

import ezdxf
import pytest

from greenplan.domain.errors import ExportError
from greenplan.export.entity_fingerprint import EntityFingerprinter
from greenplan.export.plan_exporter import PlanExporter

from fixtures.export_pipeline import ExportRun, run_synthetic_export
from fixtures.placement_factory import street_site

GENERATED_LAYER = re.compile(r"^AI_[A-Z0-9_-]+$")
PNG_SIGNATURE = b"\x89PNG"


@pytest.fixture(scope="module")
def run(knowledge_root: Path, tmp_path_factory: pytest.TempPathFactory) -> ExportRun:
    return run_synthetic_export(knowledge_root, tmp_path_factory.mktemp("export"))


def generated_inserts(document, layer_prefix: str) -> list:
    return [
        entity
        for entity in document.modelspace().query("INSERT")
        if entity.dxf.layer.startswith(layer_prefix)
    ]


def test_source_entities_and_layers_are_untouched(run: ExportRun) -> None:
    fingerprinter = EntityFingerprinter()
    source = ezdxf.readfile(run.source)
    output = ezdxf.readfile(run.output)
    difference = fingerprinter.compare(
        fingerprinter.modelspace_fingerprints(source), fingerprinter.modelspace_fingerprints(output)
    )
    assert difference.is_intact
    source_layers = {layer.dxf.name: layer.dxf.color for layer in source.layers}
    assert {name: output.layers.get(name).dxf.color for name in source_layers} == source_layers


def test_every_new_layer_is_latin_and_prefixed(run: ExportRun) -> None:
    source_layers = {layer.dxf.name for layer in ezdxf.readfile(run.source).layers}
    new_layers = {layer.dxf.name for layer in ezdxf.readfile(run.output).layers} - source_layers
    assert new_layers
    assert all(GENERATED_LAYER.match(name) for name in new_layers)


def test_plants_are_inserted_with_identity_attribute_and_xdata(run: ExportRun) -> None:
    inserts = generated_inserts(ezdxf.readfile(run.output), "AI_PL_")
    identifiers = {insert.get_attrib_text("ID") for insert in inserts}
    assert identifiers == {plant.plant_id for plant in run.report.plants}
    for insert in inserts:
        xdata = insert.get_xdata("GREENPLAN")
        assert xdata[0].value == insert.get_attrib_text("ID")
        assert all(attribute.dxf.layer == insert.dxf.layer for attribute in insert.attribs)


def test_species_layers_follow_species_keys(run: ExportRun) -> None:
    inserts = generated_inserts(ezdxf.readfile(run.output), "AI_PL_")
    species_by_id = {plant.plant_id: plant.species.key.upper() for plant in run.report.plants}
    assert all(species_by_id[insert.get_attrib_text("ID")] in insert.dxf.layer for insert in inserts)


def test_rejections_zones_and_meta_are_written(run: ExportRun) -> None:
    output = ezdxf.readfile(run.output)
    counts = run.summary.entities_by_layer
    rejection_inserts = generated_inserts(output, "AI_REJECTED")
    assert len(rejection_inserts) == len(run.report.rejections) == counts["AI_REJECTED"]
    restricted = output.modelspace().query('LWPOLYLINE[layer=="AI_ZONE_RESTRICTED"]')
    assert len(restricted) > 0 and all(polyline.closed for polyline in restricted)
    assert len(output.modelspace().query('MTEXT[layer=="AI_META"]')) == 1


def test_output_passes_audit(run: ExportRun) -> None:
    assert not ezdxf.readfile(run.output).audit().has_errors


def test_exporting_over_generated_content_is_refused(
    run: ExportRun, knowledge_root: Path, tmp_path: Path
) -> None:
    exporter = PlanExporter.from_knowledge(knowledge_root)
    with pytest.raises(ExportError):
        exporter.export(run.output, tmp_path / "again.dxf", street_site(), run.plan, run.report, "now")
    with pytest.raises(ExportError):
        exporter.export(run.source, run.source, street_site(), run.plan, run.report, "now")


def test_preview_is_a_png(run: ExportRun) -> None:
    assert run.preview.read_bytes()[:4] == PNG_SIGNATURE
