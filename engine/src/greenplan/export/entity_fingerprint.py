import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ezdxf import path as ezdxf_path
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic

FLOAT_DECIMALS = 6
FLATTENING_DISTANCE = 0.01
COMPARED_ATTRIBUTES = (
    "layer",
    "color",
    "true_color",
    "linetype",
    "lineweight",
    "flags",
    "name",
    "text",
    "insert",
    "xscale",
    "yscale",
    "zscale",
    "rotation",
    "start",
    "end",
    "center",
    "radius",
    "height",
)
GEOMETRY_ERRORS = (TypeError, ValueError, ArithmeticError)


@dataclass(frozen=True, slots=True)
class EntityFingerprint:
    handle: str
    dxftype: str
    layer: str
    digest: str


@dataclass(frozen=True, slots=True)
class IntegrityDifference:
    missing_handles: tuple[str, ...]
    changed_handles: tuple[str, ...]

    @property
    def is_intact(self) -> bool:
        return not self.missing_handles and not self.changed_handles


class EntityFingerprinter:
    def fingerprint(self, entity: DXFGraphic) -> EntityFingerprint:
        payload = f"{_attributes_text(entity)}|{_geometry_text(entity)}"
        return EntityFingerprint(
            handle=entity.dxf.handle,
            dxftype=entity.dxftype(),
            layer=entity.dxf.layer,
            digest=hashlib.sha1(payload.encode("utf-8")).hexdigest(),
        )

    def modelspace_fingerprints(self, document: Drawing) -> dict[str, EntityFingerprint]:
        return {entity.dxf.handle: self.fingerprint(entity) for entity in document.modelspace()}

    def compare(
        self, before: Mapping[str, EntityFingerprint], after: Mapping[str, EntityFingerprint]
    ) -> IntegrityDifference:
        missing = tuple(sorted(handle for handle in before if handle not in after))
        changed = tuple(
            sorted(handle for handle, print_ in before.items() if handle in after and after[handle] != print_)
        )
        return IntegrityDifference(missing, changed)


def _attributes_text(entity: DXFGraphic) -> str:
    values = []
    for key in COMPARED_ATTRIBUTES:
        if not entity.dxf.is_supported(key):
            continue
        value = entity.dxf.get(key)
        values.append(f"{key}={_value_text(entity.dxf.get_default(key) if value is None else value)}")
    return ";".join(values)


def _value_text(value: Any) -> str:
    if value is None or isinstance(value, str | bool):
        return str(value)
    if isinstance(value, int | float):
        return f"{float(value):.{FLOAT_DECIMALS}f}"
    if isinstance(value, Iterable):
        return ",".join(_value_text(float(item)) for item in value)
    return str(value)


def _geometry_text(entity: DXFGraphic) -> str:
    try:
        vertices = list(ezdxf_path.make_path(entity).flattening(FLATTENING_DISTANCE))
    except GEOMETRY_ERRORS:
        return ""
    return ";".join(f"{vertex.x:.{FLOAT_DECIMALS}f},{vertex.y:.{FLOAT_DECIMALS}f}" for vertex in vertices)
