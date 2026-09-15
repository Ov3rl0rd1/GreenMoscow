from pathlib import Path

import ezdxf
import pytest

from greenplan.domain.decisions import ACCEPTED
from greenplan.verify.plan_verifier import PlanVerifier
from greenplan.verify.verification_model import (
    CONDITION_NOT_DECLARED,
    DUPLICATE_PLANT_ID,
    MISSING_IDENTITY,
    VerificationReport,
)
from greenplan.verify.verification_writers import (
    JSON_VERIFICATION_NAME,
    write_verification_json,
    write_verification_markdown,
)

from fixtures.export_pipeline import ExportRun, run_synthetic_export


@pytest.fixture(scope="module")
def run(knowledge_root: Path, tmp_path_factory: pytest.TempPathFactory) -> ExportRun:
    return run_synthetic_export(knowledge_root, tmp_path_factory.mktemp("verification"))


@pytest.fixture(scope="module")
def verifier(knowledge_root: Path) -> PlanVerifier:
    return PlanVerifier.from_knowledge(knowledge_root)


def first_tree_insert(document):
    return next(
        entity
        for entity in document.modelspace().query("INSERT")
        if entity.dxf.layer.startswith("AI_PL_TREES_")
    )


def add_tree_copy(document, template, identifier: str, position: tuple[float, float], status: str) -> None:
    insert = document.modelspace().add_blockref(
        template.dxf.name, position, dxfattribs={"layer": template.dxf.layer}
    )
    insert.add_auto_attribs({"ID": identifier})
    tags = [(tag.code, tag.value) for tag in template.get_xdata("GREENPLAN")]
    tags[0] = (1000, identifier)
    tags[1] = (1000, status)
    insert.set_xdata("GREENPLAN", tags)


def tampered_output(run: ExportRun, path: Path, change) -> Path:
    document = ezdxf.readfile(run.output)
    change(document)
    document.saveas(path)
    return path


def codes_for(report: VerificationReport, plant_id: str) -> set[str]:
    return {violation.code for violation in report.violations if violation.plant_id == plant_id}


def test_generated_plan_passes_independent_verification(run: ExportRun, verifier: PlanVerifier) -> None:
    report = verifier.verify(run.source, run.output, run.site)
    assert report.violations == ()
    assert report.integrity.is_intact
    assert report.plants_checked == len(run.report.plants)


def test_injected_tree_on_gas_pipeline_is_caught(
    run: ExportRun, verifier: PlanVerifier, tmp_path: Path
) -> None:
    def inject(document) -> None:
        add_tree_copy(document, first_tree_insert(document), "T-9999", (50.0, 15.0), ACCEPTED)

    report = verifier.verify(run.source, tampered_output(run, tmp_path / "gas.dxf", inject), run.site)
    assert "sp42_gas_tree" in codes_for(report, "T-9999")
    assert not report.is_valid


def test_accepted_tree_inside_protection_zone_is_caught(
    run: ExportRun, verifier: PlanVerifier, tmp_path: Path
) -> None:
    def inject(document) -> None:
        add_tree_copy(document, first_tree_insert(document), "T-9998", (97.0, 13.2), ACCEPTED)

    report = verifier.verify(run.source, tampered_output(run, tmp_path / "zone.dxf", inject), run.site)
    assert CONDITION_NOT_DECLARED in codes_for(report, "T-9998")


def test_duplicate_and_unidentified_plants_are_caught(
    run: ExportRun, verifier: PlanVerifier, tmp_path: Path
) -> None:
    def inject(document) -> None:
        template = first_tree_insert(document)
        add_tree_copy(
            document, template, template.get_attrib_text("ID"), (template.dxf.insert.x, 19.0), ACCEPTED
        )
        document.modelspace().add_blockref(
            template.dxf.name, (40.0, 11.0), dxfattribs={"layer": template.dxf.layer}
        )

    report = verifier.verify(run.source, tampered_output(run, tmp_path / "format.dxf", inject), run.site)
    codes = {violation.code for violation in report.violations}
    assert {DUPLICATE_PLANT_ID, MISSING_IDENTITY} <= codes


def test_changed_source_entity_and_layer_are_caught(
    run: ExportRun, verifier: PlanVerifier, tmp_path: Path
) -> None:
    def tamper(document) -> None:
        gas_line = next(
            entity for entity in document.modelspace().query("LINE") if entity.dxf.layer == "Газопровод"
        )
        gas_line.dxf.end = (110, 16)
        document.layers.get("_ГЗН-ГЗН").color = 5

    report = verifier.verify(run.source, tampered_output(run, tmp_path / "source.dxf", tamper), run.site)
    assert len(report.integrity.changed_handles) == 1
    assert report.integrity.changed_layers == ("_ГЗН-ГЗН",)
    assert not report.is_valid


def test_verification_reports_are_written(run: ExportRun, verifier: PlanVerifier, tmp_path: Path) -> None:
    report = verifier.verify(run.source, run.output, run.site)
    json_path = write_verification_json(report, tmp_path)
    markdown_path = write_verification_markdown(report, tmp_path)
    assert json_path.name == JSON_VERIFICATION_NAME
    assert '"is_valid": true' in json_path.read_text(encoding="utf-8")
    assert "**пройдена**" in markdown_path.read_text(encoding="utf-8")
