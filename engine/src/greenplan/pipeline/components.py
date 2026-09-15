from dataclasses import dataclass
from pathlib import Path

from greenplan.explain.report_builder import ReportBuilder
from greenplan.explain.report_writers import ReportWriterSet
from greenplan.export.plan_exporter import PlanExporter
from greenplan.export.preview_renderer import PreviewRenderer
from greenplan.ingest.drawing_content_reader import DrawingContentReader
from greenplan.ingest.drawing_file_opener import DrawingFileOpener, DxfDocumentLoader
from greenplan.ingest.drawing_set_builder import DrawingSetBuilder
from greenplan.ingest.dwg_converter import LibreDwgConverter
from greenplan.ingest.xref_reference_reader import XrefReferenceReader
from greenplan.pipeline.run_config import RunConfig
from greenplan.placement.planting_plan import PlantingPlanComposer
from greenplan.recognition.site_model_builder import SiteModelBuilder
from greenplan.species.species_selector import SpeciesSelectorFactory
from greenplan.verify.plan_verifier import PlanVerifier


@dataclass(frozen=True)
class PipelineComponents:
    opener: DrawingFileOpener
    drawing_set_builder: DrawingSetBuilder
    content_reader: DrawingContentReader
    site_builder: SiteModelBuilder
    composer: PlantingPlanComposer
    species_factory: SpeciesSelectorFactory
    report_builder: ReportBuilder
    report_writers: ReportWriterSet
    exporter: PlanExporter
    preview_renderer: PreviewRenderer
    verifier: PlanVerifier

    @classmethod
    def assemble(
        cls, knowledge_root: Path, config: RunConfig, dwg2dxf: Path | None, cache_directory: Path
    ) -> "PipelineComponents":
        converter = LibreDwgConverter(dwg2dxf, cache_directory) if dwg2dxf is not None else None
        opener = DrawingFileOpener(DxfDocumentLoader(), converter)
        return cls(
            opener=opener,
            drawing_set_builder=DrawingSetBuilder(opener, XrefReferenceReader()),
            content_reader=DrawingContentReader(),
            site_builder=SiteModelBuilder.from_knowledge(knowledge_root, config.recognition),
            composer=PlantingPlanComposer.from_knowledge(knowledge_root, config.placement, config.design),
            species_factory=SpeciesSelectorFactory.from_knowledge(
                knowledge_root, config.species, config.design
            ),
            report_builder=ReportBuilder.from_knowledge(
                knowledge_root, config.explanation.max_satisfied_clearances
            ),
            report_writers=ReportWriterSet.default(),
            exporter=PlanExporter.from_knowledge(knowledge_root, config.export),
            preview_renderer=PreviewRenderer(config.preview),
            verifier=PlanVerifier.from_knowledge(
                knowledge_root, config.export, config.design, config.placement, config.verification
            ),
        )
