from dataclasses import dataclass, replace
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
from greenplan.knowledge.territory_catalog import TerritoryCatalog
from greenplan.pipeline.run_config import RunConfig
from greenplan.pipeline.site_cache import SiteCache
from greenplan.placement.guidance import GuidanceFactory, rule_guidance
from greenplan.placement.planting_plan import PlantingPlanComposer
from greenplan.recognition.site_model_builder import SiteModelBuilder
from greenplan.species.species_selector import SpeciesSelectorFactory
from greenplan.verify.plan_verifier import PlanVerifier

SITE_CACHE_FOLDER = "sites"


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
    site_cache: SiteCache | None = None

    @classmethod
    def assemble(
        cls,
        knowledge_root: Path,
        config: RunConfig,
        dwg2dxf: Path | None,
        cache_directory: Path,
        guidance: GuidanceFactory = rule_guidance,
    ) -> "PipelineComponents":
        converter = LibreDwgConverter(dwg2dxf, cache_directory) if dwg2dxf is not None else None
        opener = DrawingFileOpener(DxfDocumentLoader(), converter)
        territories = TerritoryCatalog.from_knowledge(knowledge_root)
        category = territories.category(config.territory.category or None)
        placement = replace(config.placement, density_context=category.density_context)
        return cls(
            opener=opener,
            drawing_set_builder=DrawingSetBuilder(opener, XrefReferenceReader()),
            content_reader=DrawingContentReader(),
            site_builder=SiteModelBuilder.from_knowledge(knowledge_root, config.recognition),
            composer=PlantingPlanComposer.from_knowledge(knowledge_root, placement, config.design, guidance),
            species_factory=SpeciesSelectorFactory.from_knowledge(
                knowledge_root, config.species, config.design, category.category_id
            ),
            report_builder=ReportBuilder.from_knowledge(
                knowledge_root, config.explanation.max_satisfied_clearances
            ),
            report_writers=ReportWriterSet.default(),
            exporter=PlanExporter.from_knowledge(knowledge_root, config.export),
            preview_renderer=PreviewRenderer(config.preview),
            verifier=PlanVerifier.from_knowledge(
                knowledge_root, config.export, config.design, placement, config.verification
            ),
            site_cache=SiteCache.for_recognition(
                cache_directory / SITE_CACHE_FOLDER, knowledge_root, config.recognition
            ),
        )
