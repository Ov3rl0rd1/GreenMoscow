from dataclasses import dataclass
from pathlib import Path

from greenplan.domain.site import SiteModel
from greenplan.explain.report_builder import ReportBuilder
from greenplan.explain.report_model import PlantingReport
from greenplan.export.plan_exporter import ExportSummary, PlanExporter
from greenplan.export.preview_renderer import PreviewRenderer, PreviewSettings
from greenplan.placement.planting_plan import PlantingPlan, PlantingPlanComposer
from greenplan.species.species_selector import SpeciesSelectorFactory

from fixtures.drawing_factory import (
    add_block_reference,
    add_hatch,
    add_line,
    add_polyline,
    add_text,
    create_document,
    rectangle,
    save_document,
)
from fixtures.placement_factory import street_site

GENERATED_AT = "2026-09-15T12:00"


@dataclass(frozen=True)
class ExportRun:
    source: Path
    output: Path
    preview: Path
    site: SiteModel
    plan: PlantingPlan
    report: PlantingReport
    summary: ExportSummary


def source_drawing(path: Path) -> Path:
    document = create_document()
    add_polyline(document, "ДВ_ГП_П_Граница работ", rectangle(0, -2, 100, 30), closed=True)
    add_line(document, "Газопровод", (-10, 15), (110, 15))
    add_text(document, "Газопровод", "d=110н.д.п/э", (20, 15.5))
    add_hatch(document, "_ГЗН-ГЗН", rectangle(0, 10, 100, 20))
    add_block_reference(document, "!!!_1. Дендра_сохранить", "SURVEY_TREE", (70, 18), {"N": "12"})
    return save_document(document, path)


def run_synthetic_export(knowledge_root: Path, directory: Path) -> ExportRun:
    source = source_drawing(directory / "source.dxf")
    site = street_site()
    plan = PlantingPlanComposer.from_knowledge(knowledge_root).compose(site)
    selector = SpeciesSelectorFactory.from_knowledge(knowledge_root).for_site(site)
    species = selector.assign(plan.trees + plan.shrubs)
    report = ReportBuilder.from_knowledge(knowledge_root).build("Синтетическая улица", site, plan, species)
    output = directory / "result.dxf"
    exporter = PlanExporter.from_knowledge(knowledge_root)
    summary = exporter.export(source, output, site, plan, report, GENERATED_AT)
    preview = PreviewRenderer(PreviewSettings(figure_size_in=4.0, dpi=60)).render(
        site, plan.tree_zones, report, directory / "preview.png"
    )
    return ExportRun(source, output, preview, site, plan, report, summary)
