import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.domain.errors import GreenPlanError
from greenplan.domain.site import SiteModel
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.knowledge.pilot_objects import PilotCatalog, PilotObject
from greenplan.verify.independent_norm_checker import IndependentNormChecker
from greenplan.verify.verification_model import PlacedPlant
from greenplan_ml.reference_extractor import ReferencePlanting, ReferencePlantingExtractor
from greenplan_ml.site_loader import SiteLoader
from greenplan_ml.targets import SpeciesCrownLookup

AUDIT_JSON_NAME = "reference_audit.json"
AUDIT_MARKDOWN_NAME = "reference_audit.md"
ACCEPTED_STATUS = "accepted"
REFERENCE_LAYER = "reference"


@dataclass(frozen=True, slots=True)
class ObjectAudit:
    object_id: str
    level: str
    checked: bool
    reason: str = ""
    plantings: int = 0
    outside_plantable: int = 0
    violations: int = 0
    violating_plants: int = 0
    by_rule: tuple[tuple[str, int], ...] = ()

    @property
    def violation_share(self) -> float:
        return self.violating_plants / self.plantings if self.plantings else 0.0


class ReferenceAuditor:
    def __init__(
        self,
        loader: SiteLoader,
        extractor: ReferencePlantingExtractor,
        checker: IndependentNormChecker,
        crowns: SpeciesCrownLookup,
    ) -> None:
        self._loader = loader
        self._extractor = extractor
        self._checker = checker
        self._crowns = crowns

    @classmethod
    def from_knowledge(
        cls,
        knowledge_root: Path,
        dwg2dxf: Path | None = None,
        cache_directory: Path | None = None,
        design: DesignConstraints | None = None,
    ) -> "ReferenceAuditor":
        constraints = design or DesignConstraints()
        repository = NormsRepository.from_knowledge(knowledge_root)
        return cls(
            loader=SiteLoader.from_knowledge(knowledge_root, dwg2dxf, cache_directory),
            extractor=ReferencePlantingExtractor.from_knowledge(knowledge_root),
            checker=IndependentNormChecker(
                repository,
                constraints.unknown_overhead_voltage_kv,
                constraints.clearance_tolerance_m,
                constraints.obstacle_search_margin_m,
                constraints.active_activations(),
            ),
            crowns=SpeciesCrownLookup.from_knowledge(knowledge_root),
        )

    def audit(self, item: PilotObject, dataset_root: Path) -> ObjectAudit:
        try:
            loaded = self._loader.load(dataset_root / item.input_path, dataset_root / item.object_folder)
            content = self._loader.read(dataset_root / item.reference_path)
        except GreenPlanError as error:
            return ObjectAudit(item.object_id, item.level, False, f"{type(error).__name__}: {error}")
        plantings = self._extractor.extract(content, item.layer_scheme)
        if not plantings.plantings:
            return ObjectAudit(item.object_id, item.level, False, "в проектном решении нет посадок")
        return self._audit_plantings(item, loaded.site, plantings.plantings)

    def audit_all(
        self,
        catalog: PilotCatalog,
        dataset_root: Path,
        levels: Sequence[str] | None = None,
        object_ids: Sequence[str] | None = None,
    ) -> list[ObjectAudit]:
        return [self.audit(item, dataset_root) for item in catalog.selected(levels, object_ids)]

    def _audit_plantings(
        self, item: PilotObject, site: SiteModel, plantings: Sequence[ReferencePlanting]
    ) -> ObjectAudit:
        plants = [self._placed(index, planting) for index, planting in enumerate(plantings)]
        violations = self._checker.violations(plants, site)
        by_rule = Counter(violation.code for violation in violations)
        return ObjectAudit(
            object_id=item.object_id,
            level=item.level,
            checked=True,
            plantings=len(plants),
            outside_plantable=sum(
                1 for planting in plantings if not site.plantable_surface.contains(planting.position)
            ),
            violations=len(violations),
            violating_plants=len({violation.plant_id for violation in violations}),
            by_rule=tuple(by_rule.most_common()),
        )

    def _placed(self, index: int, planting: ReferencePlanting) -> PlacedPlant:
        crown = self._crowns.crown_for(planting.target, planting.species_ru)
        return PlacedPlant(
            f"{planting.target}-{index}",
            planting.target,
            planting.species_ru,
            ACCEPTED_STATUS,
            planting.position,
            crown,
            REFERENCE_LAYER,
            f"{planting.target}-{index}",
        )


def write_audit_report(directory: Path, audits: Sequence[ObjectAudit]) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / AUDIT_JSON_NAME
    json_path.write_text(
        json.dumps([asdict(item) for item in audits], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_path = directory / AUDIT_MARKDOWN_NAME
    markdown_path.write_text(render_audit_markdown(audits), encoding="utf-8")
    return json_path, markdown_path


def render_audit_markdown(audits: Sequence[ObjectAudit]) -> str:
    lines = [
        "# Аудит эталонных проектов по нормам",
        "",
        "Проверка проектных решений датасета тем же независимым нормативным контролем, что и",
        "наш результат: те же правила, те же измерения между поверхностями.",
        "",
        "| Объект | Уровень | Посадок | Вне газона | Нарушений | Посадок с нарушением | Доля |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in audits:
        if not item.checked:
            lines.append(f"| {item.object_id} | {item.level} | — | — | — | — | {item.reason} |")
            continue
        lines.append(
            f"| {item.object_id} | {item.level} | {item.plantings} | {item.outside_plantable} | "
            f"{item.violations} | {item.violating_plants} | {item.violation_share:.0%} |"
        )
    for item in audits:
        if item.checked and item.by_rule:
            listed = ", ".join(f"{rule} — {count}" for rule, count in item.by_rule[:5])
            lines.extend(["", f"**{item.object_id}**: {listed}"])
    return "\n".join(lines) + "\n"
