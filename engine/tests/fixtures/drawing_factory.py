from collections.abc import Sequence
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing

METERS_UNIT_CODE = 6
Coordinate = tuple[float, float]


def create_document() -> Drawing:
    document = ezdxf.new("R2013", setup=False)
    document.header["$INSUNITS"] = METERS_UNIT_CODE
    return document


def ensure_layer(document: Drawing, layer: str) -> None:
    if layer not in document.layers:
        document.layers.add(layer)


def add_line(document: Drawing, layer: str, start: Coordinate, end: Coordinate) -> None:
    ensure_layer(document, layer)
    document.modelspace().add_line(start, end, dxfattribs={"layer": layer})


def add_polyline(document: Drawing, layer: str, points: Sequence[Coordinate], closed: bool = False) -> None:
    ensure_layer(document, layer)
    document.modelspace().add_lwpolyline(points, close=closed, dxfattribs={"layer": layer})


def add_circle(document: Drawing, layer: str, center: Coordinate, radius: float) -> None:
    ensure_layer(document, layer)
    document.modelspace().add_circle(center, radius, dxfattribs={"layer": layer})


def add_text(
    document: Drawing, layer: str, text: str, position: Coordinate, rotation_deg: float = 0.0
) -> None:
    ensure_layer(document, layer)
    document.modelspace().add_text(
        text, dxfattribs={"layer": layer, "insert": position, "rotation": rotation_deg, "height": 0.5}
    )


def add_hatch(
    document: Drawing,
    layer: str,
    outer: Sequence[Coordinate],
    holes: Sequence[Sequence[Coordinate]] = (),
) -> None:
    ensure_layer(document, layer)
    hatch = document.modelspace().add_hatch(dxfattribs={"layer": layer})
    hatch.paths.add_polyline_path(outer, is_closed=True)
    for hole in holes:
        hatch.paths.add_polyline_path(hole, is_closed=True)


def add_block_reference(
    document: Drawing,
    layer: str,
    block_name: str,
    position: Coordinate,
    attributes: dict[str, str] | None = None,
) -> None:
    ensure_layer(document, layer)
    if block_name not in document.blocks:
        block = document.blocks.new(block_name)
        block.add_circle((0, 0), 0.2)
        for tag in attributes or {}:
            block.add_attdef(tag, (0, 0))
    reference = document.modelspace().add_blockref(block_name, position, dxfattribs={"layer": layer})
    if attributes:
        reference.add_auto_attribs(attributes)


def add_xref(document: Drawing, block_name: str, declared_path: str, insert: Coordinate = (0.0, 0.0)) -> None:
    document.add_xref_def(declared_path, block_name)
    document.modelspace().add_blockref(block_name, insert)


def rectangle(min_x: float, min_y: float, max_x: float, max_y: float) -> list[Coordinate]:
    return [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]


def save_document(document: Drawing, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(path)
    return path
