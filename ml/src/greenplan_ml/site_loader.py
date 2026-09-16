from dataclasses import dataclass
from pathlib import Path

from greenplan.constraints.clearance_meter import ClearanceMeter
from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.requirement_resolver import RequirementResolver
from greenplan.constraints.zone_builder import ZoneBuilder
from greenplan.domain.drawing import DrawingContent
from greenplan.domain.norms import TREE
from greenplan.domain.site import SiteModel
from greenplan.ingest.drawing_content_reader import DrawingContentReader
from greenplan.ingest.drawing_file_opener import DrawingFileOpener, DxfDocumentLoader
from greenplan.ingest.drawing_set_builder import DrawingSetBuilder
from greenplan.ingest.dwg_converter import LibreDwgConverter
from greenplan.ingest.xref_reference_reader import XrefReferenceReader
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.planting_profile import PlantingProfile
from greenplan.placement.planting_zones import PlantingZoneBuilder, PlantingZones
from greenplan.placement.raster import SiteRaster
from greenplan.placement.score_maps import RuleScoreMap
from greenplan.placement.site_rasterizer import SiteRasterizer
from greenplan.recognition.settings import RecognitionSettings
from greenplan.recognition.site_model_builder import SiteModelBuilder


@dataclass(frozen=True, slots=True, eq=False)
class LoadedSite:
    site: SiteModel
    raster: SiteRaster
    unresolved_references: tuple[str, ...]


class SiteLoader:
    def __init__(
        self,
        drawing_set_builder: DrawingSetBuilder,
        content_reader: DrawingContentReader,
        site_builder: SiteModelBuilder,
        zone_builder: PlantingZoneBuilder,
        rasterizer: SiteRasterizer,
        tree_profile: PlantingProfile,
    ) -> None:
        self._drawing_set_builder = drawing_set_builder
        self._content_reader = content_reader
        self._site_builder = site_builder
        self._zone_builder = zone_builder
        self._rasterizer = rasterizer
        self._tree_profile = tree_profile

    @classmethod
    def from_knowledge(
        cls,
        knowledge_root: Path,
        dwg2dxf: Path | None = None,
        cache_directory: Path | None = None,
        cell_size_m: float | None = None,
        placement: PlacementSettings | None = None,
        design: DesignConstraints | None = None,
        recognition: RecognitionSettings | None = None,
    ) -> "SiteLoader":
        settings = placement or PlacementSettings()
        constraints = design or DesignConstraints()
        repository = NormsRepository.from_knowledge(knowledge_root)
        resolver = RequirementResolver(
            repository, constraints.unknown_overhead_voltage_kv, constraints.active_activations()
        )
        converter = (
            LibreDwgConverter(dwg2dxf, cache_directory)
            if dwg2dxf is not None and cache_directory is not None
            else None
        )
        opener = DrawingFileOpener(DxfDocumentLoader(), converter)
        return cls(
            drawing_set_builder=DrawingSetBuilder(opener, XrefReferenceReader()),
            content_reader=DrawingContentReader(),
            site_builder=SiteModelBuilder.from_knowledge(knowledge_root, recognition),
            zone_builder=PlantingZoneBuilder(
                ZoneBuilder(resolver, ClearanceMeter(repository.defaults)), resolver, constraints
            ),
            rasterizer=SiteRasterizer(cell_size_m or settings.cell_size_m),
            tree_profile=tree_profile_of(settings),
        )

    def read(self, path: Path, search_root: Path | None = None) -> DrawingContent:
        drawing_set = self._drawing_set_builder.build(path, search_root)
        return self._content_reader.read(drawing_set)

    def load(self, path: Path, search_root: Path | None = None) -> LoadedSite:
        drawing_set = self._drawing_set_builder.build(path, search_root)
        content = self._content_reader.read(drawing_set)
        site = self._site_builder.build(content, drawing_set.unresolved_references)
        return LoadedSite(site, self.rasterize(site), drawing_set.unresolved_references)

    def rasterize(self, site: SiteModel) -> SiteRaster:
        return self._rasterizer.rasterize(site, self.zones_for(site), self._tree_profile.reference_edge_kind)

    def zones_for(self, site: SiteModel) -> PlantingZones:
        return self._zone_builder.build(site, self._tree_profile, ())


def tree_profile_of(settings: PlacementSettings) -> PlantingProfile:
    return PlantingProfile(
        target=TREE,
        crown_diameter_m=settings.tree_crown_diameter_m,
        spacing_m=0.0,
        max_count=None,
        reference_edge_kind=settings.tree_reference_edge_kind,
        score_map=RuleScoreMap(settings.tree_score),
        allow_conditional=settings.allow_conditional,
        planned_plant_clearance_m=0.0,
    )
