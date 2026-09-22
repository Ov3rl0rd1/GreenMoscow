from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.domain.errors import ConfigurationError
from greenplan.explain.explanation_builder import DEFAULT_MAX_SATISFIED_CLEARANCES
from greenplan.export.export_settings import ExportSettings
from greenplan.export.preview_renderer import PreviewSettings
from greenplan.knowledge.yaml_loader import load_yaml_mapping
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.recognition.settings import RecognitionSettings
from greenplan.species.species_settings import SpeciesSettings
from greenplan.verify.plan_verifier import VerificationSettings

ROOT_CONTEXT = "config"


@dataclass(frozen=True, slots=True)
class TerritorySettings:
    category: str = ""


@dataclass(frozen=True, slots=True)
class ExplanationSettings:
    max_satisfied_clearances: int = DEFAULT_MAX_SATISFIED_CLEARANCES


@dataclass(frozen=True, slots=True)
class RunConfig:
    recognition: RecognitionSettings = field(default_factory=RecognitionSettings)
    design: DesignConstraints = field(default_factory=DesignConstraints)
    placement: PlacementSettings = field(default_factory=PlacementSettings)
    species: SpeciesSettings = field(default_factory=SpeciesSettings)
    territory: TerritorySettings = field(default_factory=TerritorySettings)
    explanation: ExplanationSettings = field(default_factory=ExplanationSettings)
    export: ExportSettings = field(default_factory=ExportSettings)
    preview: PreviewSettings = field(default_factory=PreviewSettings)
    verification: VerificationSettings = field(default_factory=VerificationSettings)


class RunConfigLoader:
    def load(self, path: Path | None) -> RunConfig:
        if path is None:
            return RunConfig()
        return apply_overrides(RunConfig(), load_yaml_mapping(path), ROOT_CONTEXT)


def apply_overrides(instance: Any, overrides: Any, context: str) -> Any:
    if not isinstance(overrides, Mapping):
        raise ConfigurationError(f"section '{context}' must be a mapping")
    known = {item.name for item in fields(instance)}
    changes: dict[str, Any] = {}
    for key, value in overrides.items():
        path = f"{context}.{key}"
        if key not in known:
            raise ConfigurationError(f"unknown setting '{path}'")
        current = getattr(instance, key)
        changes[key] = (
            apply_overrides(current, value, path) if is_dataclass(current) else coerced(current, value, path)
        )
    return replace(instance, **changes)


def coerced(current: Any, value: Any, path: str) -> Any:
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
    elif isinstance(current, float):
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    elif isinstance(current, int):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    elif isinstance(current, str) and isinstance(value, str):
        return value
    raise ConfigurationError(f"invalid value for '{path}': {value!r}")
