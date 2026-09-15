from dataclasses import dataclass

from shapely.geometry import Point

MISSING_IDENTITY = "missing_identity"
DUPLICATE_PLANT_ID = "duplicate_plant_id"
CONDITION_NOT_DECLARED = "condition_not_declared"
SPACING_VIOLATED = "spacing_violated"

FORMAT_SEVERITY = "format"
SITE_SEVERITY = "site"
DESIGN_SEVERITY = "design"
DECLARATION_SEVERITY = "declaration"


@dataclass(frozen=True, slots=True)
class PlacedPlant:
    plant_id: str
    plant_type: str
    species_key: str
    status: str
    position: Point
    crown_diameter_m: float
    layer: str
    handle: str


@dataclass(frozen=True, slots=True)
class VerificationViolation:
    plant_id: str
    code: str
    severity: str
    actual_m: float | None = None
    required_m: float | None = None
    obstacle_kind: str = ""


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    missing_handles: tuple[str, ...]
    changed_handles: tuple[str, ...]
    changed_layers: tuple[str, ...]
    missing_blocks: tuple[str, ...]

    @property
    def is_intact(self) -> bool:
        return not (
            self.missing_handles or self.changed_handles or self.changed_layers or self.missing_blocks
        )


@dataclass(frozen=True, slots=True)
class VerificationReport:
    output_path: str
    plants_checked: int
    violations: tuple[VerificationViolation, ...]
    integrity: IntegrityReport

    @property
    def is_valid(self) -> bool:
        return not self.violations and self.integrity.is_intact
