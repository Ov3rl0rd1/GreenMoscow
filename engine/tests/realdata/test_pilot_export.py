import ezdxf
import pytest

from greenplan.domain.site import SiteModel
from greenplan.explain.report_model import PlantingReport
from greenplan.export.entity_fingerprint import EntityFingerprinter
from greenplan.verify.plan_verifier import PlanVerifier

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


def test_export_keeps_source_entities_and_adds_every_plant(
    bagritskogo_export, bagritskogo_report: PlantingReport
) -> None:
    fingerprinter = EntityFingerprinter()
    before = fingerprinter.modelspace_fingerprints(ezdxf.readfile(bagritskogo_export.source))
    after = fingerprinter.modelspace_fingerprints(ezdxf.readfile(bagritskogo_export.output))
    counts = bagritskogo_export.summary.entities_by_layer
    plant_entities = sum(count for layer, count in counts.items() if layer.startswith("AI_PL_"))
    assert fingerprinter.compare(before, after).is_intact
    assert plant_entities == len(bagritskogo_report.plants)


def test_exported_plan_passes_independent_verification(
    bagritskogo_export, bagritskogo_site: SiteModel, bagritskogo_report: PlantingReport, knowledge_root
) -> None:
    verifier = PlanVerifier.from_knowledge(knowledge_root)
    report = verifier.verify(bagritskogo_export.source, bagritskogo_export.output, bagritskogo_site)
    assert report.plants_checked == len(bagritskogo_report.plants)
    assert report.integrity.is_intact
    assert report.violations == ()
