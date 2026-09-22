import re
from dataclasses import dataclass
from pathlib import Path

from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

LAWN = "lawn"
CARRIAGEWAY = "carriageway"
SIDEWALK = "sidewalk"


@dataclass(frozen=True, slots=True)
class _NamedSurfaceLayer:
    pattern: re.Pattern[str]
    surface_class: str


@dataclass(frozen=True, slots=True)
class SurfaceLayer:
    layer: str
    existing_code: str
    target_code: str
    target_class: str | None


class SurfaceCodeCatalog:
    def __init__(
        self,
        layer_pattern: re.Pattern[str],
        classes_by_code: dict[str, str],
        named_layers: tuple[_NamedSurfaceLayer, ...],
        fallback_green_area_layers: tuple[str, ...],
    ) -> None:
        self._layer_pattern = layer_pattern
        self._classes_by_code = classes_by_code
        self._named_layers = named_layers
        self.fallback_green_area_layers = fallback_green_area_layers

    @classmethod
    def from_file(cls, path: Path) -> "SurfaceCodeCatalog":
        content = load_yaml_mapping(path)
        meta = require_key(content, "meta", path)
        classes_by_code = {
            code: surface_class
            for surface_class, codes in require_key(content, "surface_classes", path).items()
            for code in codes
        }
        named = tuple(
            _NamedSurfaceLayer(re.compile(entry["layer_regex"]), entry["class"])
            for entry in content.get("project_surface_layers", [])
        )
        fallback = tuple(content.get("fallback_green_area_layers", []))
        return cls(re.compile(meta["layer_pattern"]), classes_by_code, named, fallback)

    def parse(self, layer: str) -> SurfaceLayer | None:
        match = self._layer_pattern.match(layer)
        if match is None:
            return None
        existing = match.group("existing").strip()
        target = match.group("target").strip()
        return SurfaceLayer(layer, existing, target, self._classes_by_code.get(target))

    def surface_class(self, layer: str) -> str | None:
        parsed = self.parse(layer)
        if parsed is not None and parsed.target_class is not None:
            return parsed.target_class
        return next(
            (entry.surface_class for entry in self._named_layers if entry.pattern.search(layer)), None
        )
