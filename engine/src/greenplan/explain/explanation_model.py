from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CitationView:
    key: str
    document: str
    locator: str | None
    verification: str
    text_ru: str


@dataclass(frozen=True, slots=True)
class CompetingView:
    citation: CitationView
    required_m: float | None


@dataclass(frozen=True, slots=True)
class ClearanceView:
    rule_id: str
    rule_type: str
    severity: str
    obstacle_kind: str
    obstacle_ru: str
    obstacle_layer: str
    obstacle_source: str
    evidence: tuple[str, ...]
    measurement_ru: str
    actual_m: float
    required_m: float
    base_required_m: float
    crown_increment_m: float
    margin_m: float
    satisfied: bool
    assumed_outer_radius: bool
    condition_ru: str
    is_assumption: bool
    citations: tuple[CitationView, ...]
    crown_rule_citations: tuple[CitationView, ...]
    competing: tuple[CompetingView, ...]


@dataclass(frozen=True, slots=True)
class ViolationView:
    code: str
    text_ru: str
    actual_m: float | None
    required_m: float | None
    citations: tuple[CitationView, ...]


@dataclass(frozen=True, slots=True)
class ReasonView:
    code: str
    text_ru: str
    citations: tuple[CitationView, ...]


@dataclass(frozen=True, slots=True)
class SpeciesView:
    key: str
    name_ru: str
    latin: str
    crown_diameter_m: float
    height_m: float
    invasive_status: str
    invasive_text_ru: str
    invasive_citations: tuple[CitationView, ...]
    reasons: tuple[ReasonView, ...]


@dataclass(frozen=True, slots=True)
class PlantExplanation:
    plant_id: str
    status: str
    plant_type: str
    x: float
    y: float
    crown_diameter_m: float
    species: SpeciesView | None
    clearances: tuple[ClearanceView, ...]
    violations: tuple[ViolationView, ...]
    explanation_ru: str

    @property
    def primary_reason_code(self) -> str:
        if self.violations:
            return self.violations[0].code
        unsatisfied = [clearance for clearance in self.clearances if not clearance.satisfied]
        return unsatisfied[0].rule_id if unsatisfied else ""
