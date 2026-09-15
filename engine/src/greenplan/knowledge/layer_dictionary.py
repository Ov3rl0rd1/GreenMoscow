import re
from dataclasses import dataclass
from pathlib import Path

from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

UNKNOWN_CONFIDENCE = 0.0
AUXILIARY_CONFIDENCE = 0.8


@dataclass(frozen=True, slots=True)
class LayerClassification:
    layer: str
    kind: str | None
    is_known: bool
    status: str
    confidence: float
    evidence: tuple[str, ...]

    @property
    def is_obstacle(self) -> bool:
        return self.kind is not None


@dataclass(frozen=True, slots=True)
class _CanonicalLayer:
    name: str
    kind: str | None
    status: str
    confidence: float
    suffix: str


@dataclass(frozen=True, slots=True)
class _AuxiliaryLayer:
    pattern: re.Pattern[str]
    kind: str


@dataclass(frozen=True, slots=True)
class _Normalizer:
    pattern: re.Pattern[str]
    replacement: str


class LayerDictionary:
    def __init__(
        self,
        canonical_layers: dict[str, _CanonicalLayer],
        auxiliary_layers: tuple[_AuxiliaryLayer, ...],
        normalizers: tuple[_Normalizer, ...],
    ) -> None:
        self._canonical_layers = canonical_layers
        self._auxiliary_layers = auxiliary_layers
        self._normalizers = normalizers

    @classmethod
    def from_file(cls, path: Path) -> "LayerDictionary":
        content = load_yaml_mapping(path)
        meta = require_key(content, "meta", path)
        canonical = {
            entry["layer"]: _canonical_entry(entry) for entry in require_key(content, "layers", path)
        }
        auxiliary = tuple(
            _AuxiliaryLayer(re.compile(entry["layer_regex"]), entry["obstacle"])
            for entry in content.get("auxiliary_layers", [])
        )
        normalizers = tuple(
            _Normalizer(re.compile(entry["pattern"]), entry["replace"])
            for entry in meta.get("layer_name_normalizers", [])
        )
        return cls(canonical, auxiliary, normalizers)

    def normalize(self, layer: str) -> str:
        normalized = layer
        for normalizer in self._normalizers:
            normalized = normalizer.pattern.sub(normalizer.replacement, normalized)
        return normalized.strip()

    def classify(self, layer: str) -> LayerClassification:
        normalized = self.normalize(layer)
        canonical = self._canonical_layers.get(normalized)
        if canonical is not None:
            return self._from_canonical(layer, normalized, canonical)
        auxiliary = next((entry for entry in self._auxiliary_layers if entry.pattern.search(layer)), None)
        if auxiliary is not None:
            evidence = (f"layer:{layer}", f"pattern:{auxiliary.pattern.pattern}")
            return LayerClassification(
                layer, auxiliary.kind, True, "existing", AUXILIARY_CONFIDENCE, evidence
            )
        return LayerClassification(layer, None, False, "existing", UNKNOWN_CONFIDENCE, (f"layer:{layer}",))

    def _from_canonical(self, layer: str, normalized: str, canonical: _CanonicalLayer) -> LayerClassification:
        evidence = (f"layer:{layer}", f"mosgeotrest:{canonical.suffix}:{normalized}")
        return LayerClassification(
            layer, canonical.kind, True, canonical.status, canonical.confidence, evidence
        )


def _canonical_entry(entry: dict) -> _CanonicalLayer:
    return _CanonicalLayer(
        name=entry["layer"],
        kind=entry.get("obstacle"),
        status=entry.get("status", "existing"),
        confidence=float(entry.get("confidence", 1.0)),
        suffix=entry.get("suffix", ""),
    )
