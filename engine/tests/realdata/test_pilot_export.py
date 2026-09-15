from pathlib import Path

import ezdxf
import pytest

from greenplan.domain.site import SiteModel
from greenplan.explain.report_model import PlantingReport
from greenplan.export.entity_fingerprint import EntityFingerprinter
from greenplan.export.plan_exporter import PlanExporter
from greenplan.ingest.dwg_converter import LibreDwgConverter
from greenplan.placement.planting_plan import PlantingPlan

from fixtures.pilot_objects import LoadedPilotObject

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


def test_export_keeps_source_entities_and_adds_every_plant(
    bagritskogo: LoadedPilotObject,
    bagritskogo_site: SiteModel,
    bagritskogo_plan: PlantingPlan,
    bagritskogo_report: PlantingReport,
    dwg2dxf_path: Path,
    repository_root: Path,
    knowledge_root: Path,
    tmp_path: Path,
) -> None:
    converter = LibreDwgConverter(dwg2dxf_path, repository_root / "data" / "cache" / "converted")
    source = converter.convert(bagritskogo.drawing_set.main.path)
    output = tmp_path / "bagritskogo_greenplan.dxf"
    exporter = PlanExporter.from_knowledge(knowledge_root)
    summary = exporter.export(source, output, bagritskogo_site, bagritskogo_plan, bagritskogo_report, "test")
    fingerprinter = EntityFingerprinter()
    before = fingerprinter.modelspace_fingerprints(ezdxf.readfile(source))
    after = fingerprinter.modelspace_fingerprints(ezdxf.readfile(output))
    plant_layers = sum(
        count for layer, count in summary.entities_by_layer.items() if layer.startswith("AI_PL_")
    )
    assert fingerprinter.compare(before, after).is_intact
    assert plant_layers == len(bagritskogo_report.plants)
