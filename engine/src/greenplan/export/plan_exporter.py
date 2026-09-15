from dataclasses import dataclass
from pathlib import Path

from greenplan.domain.errors import ExportError
from greenplan.domain.site import SiteModel
from greenplan.explain.report_model import PlantingReport
from greenplan.export.export_settings import ExportSettings
from greenplan.export.layer_names import LayerNameSanitizer
from greenplan.export.plan_layer_writer import PlanLayerWriter
from greenplan.ingest.drawing_file_opener import DxfDocumentLoader
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.placement.planting_plan import PlantingPlan


@dataclass(frozen=True, slots=True)
class ExportSummary:
    output_path: Path
    entities_by_layer: dict[str, int]


class PlanExporter:
    def __init__(self, loader: DxfDocumentLoader, writer: PlanLayerWriter) -> None:
        self._loader = loader
        self._writer = writer

    @classmethod
    def from_knowledge(cls, knowledge_root: Path, settings: ExportSettings | None = None) -> "PlanExporter":
        effective = settings or ExportSettings()
        defaults = NormsRepository.from_knowledge(knowledge_root).defaults
        writer = PlanLayerWriter(
            effective,
            LayerNameSanitizer(effective.max_layer_name_length),
            defaults.trunk_diameter_at_planting_m,
        )
        return cls(DxfDocumentLoader(), writer)

    def export(
        self,
        source_dxf: Path,
        output_path: Path,
        site: SiteModel,
        plan: PlantingPlan,
        report: PlantingReport,
        generated_at: str,
    ) -> ExportSummary:
        if source_dxf.resolve() == output_path.resolve():
            raise ExportError(f"output must not overwrite the source drawing: {source_dxf}")
        document = self._loader.load(source_dxf)
        counts = self._writer.write(document, site, plan.tree_zones, report, generated_at)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.saveas(output_path)
        return ExportSummary(output_path, counts)
