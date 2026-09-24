from dataclasses import dataclass
from pathlib import Path

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.domain.site import SiteModel
from greenplan.export.entity_fingerprint import EntityFingerprinter
from greenplan.export.export_settings import ExportSettings
from greenplan.ingest.drawing_file_opener import DxfDocumentLoader
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.planting_limits import LOWER_BOUND, PlantingLimitsResolver, SpacingBounds
from greenplan.verify.generated_plan_reader import GeneratedPlanReader
from greenplan.verify.independent_norm_checker import IndependentNormChecker
from greenplan.verify.site_placement_checker import SitePlacementChecker
from greenplan.verify.source_integrity import SourceIntegrityChecker
from greenplan.verify.verification_model import VerificationReport


@dataclass(frozen=True, slots=True)
class VerificationSettings:
    distance_tolerance_m: float = 0.001
    obstacle_search_margin_m: float = 3.0


class PlanVerifier:
    def __init__(
        self,
        loader: DxfDocumentLoader,
        reader: GeneratedPlanReader,
        norm_checker: IndependentNormChecker,
        limits_resolver: PlantingLimitsResolver,
        integrity_checker: SourceIntegrityChecker,
        design: DesignConstraints,
        placement: PlacementSettings,
        settings: VerificationSettings,
    ) -> None:
        self._loader = loader
        self._reader = reader
        self._norm_checker = norm_checker
        self._limits_resolver = limits_resolver
        self._integrity_checker = integrity_checker
        self._design = design
        self._placement = placement
        self._settings = settings

    @classmethod
    def from_knowledge(
        cls,
        knowledge_root: Path,
        export_settings: ExportSettings | None = None,
        design: DesignConstraints | None = None,
        placement: PlacementSettings | None = None,
        settings: VerificationSettings | None = None,
    ) -> "PlanVerifier":
        effective = settings or VerificationSettings()
        constraints = design or DesignConstraints()
        placement_settings = placement or PlacementSettings()
        repository = NormsRepository.from_knowledge(knowledge_root)
        return cls(
            loader=DxfDocumentLoader(),
            reader=GeneratedPlanReader(export_settings or ExportSettings()),
            norm_checker=IndependentNormChecker(
                repository,
                constraints.unknown_overhead_voltage_kv,
                effective.distance_tolerance_m,
                effective.obstacle_search_margin_m,
                constraints.active_activations(),
            ),
            limits_resolver=PlantingLimitsResolver(repository, placement_settings),
            integrity_checker=SourceIntegrityChecker(EntityFingerprinter()),
            design=constraints,
            placement=placement_settings,
            settings=effective,
        )

    def verify(self, source_dxf: Path, output_dxf: Path, site: SiteModel) -> VerificationReport:
        source = self._loader.load(source_dxf)
        output = self._loader.load(output_dxf)
        plants, format_violations = self._reader.read(output)
        violations = (
            *format_violations,
            *self._norm_checker.violations(plants, site),
            *self._site_checker(site).violations(plants, site),
        )
        return VerificationReport(
            output_path=str(output_dxf),
            plants_checked=len(plants),
            violations=tuple(violations),
            integrity=self._integrity_checker.check(source, output),
        )

    def _site_checker(self, site: SiteModel) -> SitePlacementChecker:
        limits = self._limits_resolver.resolve(site, SpacingBounds(LOWER_BOUND, LOWER_BOUND))
        return SitePlacementChecker(
            self._design,
            limits.tree_spacing_m,
            limits.shrub_spacing_m,
            self._placement.min_shrub_distance_to_planned_tree_m,
            self._settings.distance_tolerance_m,
        )
