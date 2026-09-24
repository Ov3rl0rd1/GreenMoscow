from collections import Counter
from collections.abc import Iterable

from ezdxf import const
from ezdxf.document import Drawing
from ezdxf.entities import Insert
from ezdxf.layouts import Modelspace
from shapely.geometry.base import BaseGeometry

from greenplan.domain.decisions import CONDITIONALLY_ACCEPTED
from greenplan.domain.errors import ExportError
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.explain.explanation_model import ClearanceView, PlantExplanation
from greenplan.explain.number_format import format_number
from greenplan.explain.report_model import PlantingReport
from greenplan.export.export_settings import ExportSettings
from greenplan.export.layer_names import SEPARATOR, LayerNameSanitizer
from greenplan.export.shrub_groups import shrub_group_areas
from greenplan.export.symbol_blocks import SymbolBlockFactory
from greenplan.geometry.shapes import polygonal_parts
from greenplan.placement.planting_zones import PlantingZones

XDATA_STRING_CODE = 1000
XDATA_REAL_CODE = 1040
XDATA_EMPTY_VALUE = "-"
MTEXT_PARAGRAPH = "\\P"
META_TEXT_HEIGHT_FACTOR = 2.0
META_OFFSET_FACTOR = 4.0


class PlanLayerWriter:
    def __init__(
        self, settings: ExportSettings, sanitizer: LayerNameSanitizer, trunk_diameter_m: float
    ) -> None:
        self._settings = settings
        self._sanitizer = sanitizer
        self._trunk_diameter_m = trunk_diameter_m

    def write(
        self,
        document: Drawing,
        site: SiteModel,
        zones: PlantingZones,
        report: PlantingReport,
        generated_at: str,
    ) -> dict[str, int]:
        self._ensure_no_generated_content(document)
        self._register_application(document)
        modelspace = document.modelspace()
        symbols = SymbolBlockFactory(document, self._settings, self._sanitizer, self._trunk_diameter_m)
        counts: Counter[str] = Counter()
        for plant in report.plants:
            counts[self._write_plant(document, modelspace, symbols, plant)] += 1
        counts.update(self._write_root_barriers(document, modelspace, report))
        if self._settings.include_shrub_groups:
            counts.update(self._write_shrub_groups(document, modelspace, report))
        if self._settings.include_rejections:
            for rejection in report.rejections:
                counts[self._write_rejection(document, modelspace, symbols, rejection)] += 1
        if self._settings.include_zones:
            counts.update(self._write_zones(document, modelspace, site, zones))
        counts[self._write_meta(document, modelspace, site, report, generated_at)] += 1
        return dict(counts)

    def _ensure_no_generated_content(self, document: Drawing) -> None:
        prefix = f"{self._settings.layer_prefix}{SEPARATOR}"
        names = [layer.dxf.name for layer in document.layers] + [block.name for block in document.blocks]
        clashes = sorted(name for name in names if name.upper().startswith(prefix))
        if clashes:
            raise ExportError(f"source drawing already contains generated layers or blocks: {clashes[:5]}")

    def _register_application(self, document: Drawing) -> None:
        if self._settings.xdata_application not in document.appids:
            document.appids.add(self._settings.xdata_application)

    def _layer(self, document: Drawing, parts: Iterable[str], color: int) -> str:
        name = self._sanitizer.join(self._settings.layer_prefix, *parts)
        if name not in document.layers:
            document.layers.add(name, color=color)
        return name

    def _write_plant(
        self, document: Drawing, modelspace: Modelspace, symbols: SymbolBlockFactory, plant: PlantExplanation
    ) -> str:
        settings = self._settings
        is_tree = plant.plant_type == TREE
        is_conditional = plant.status == CONDITIONALLY_ACCEPTED
        species_key = plant.species.key if plant.species else plant.plant_type
        stem = settings.tree_layer_stem if is_tree else settings.shrub_layer_stem
        color = (
            settings.conditional_color
            if is_conditional
            else settings.tree_color
            if is_tree
            else settings.shrub_color
        )
        suffix = settings.conditional_suffix if is_conditional else ""
        layer = self._layer(document, (stem, species_key, suffix), color)
        insert = modelspace.add_blockref(
            symbols.plant_block(plant), (plant.x, plant.y), dxfattribs={"layer": layer}
        )
        self._attach_identity(insert, plant, layer)
        return layer

    def _write_root_barriers(
        self, document: Drawing, modelspace: Modelspace, report: PlantingReport
    ) -> Counter[str]:
        lines = [line for plant in report.plants for line in plant.root_barriers]
        if not lines:
            return Counter()
        settings = self._settings
        layer = self._layer(document, (settings.root_barrier_layer_stem,), settings.root_barrier_color)
        for points in lines:
            modelspace.add_lwpolyline(list(points), dxfattribs={"layer": layer})
        return Counter({layer: len(lines)})

    def _write_rejection(
        self,
        document: Drawing,
        modelspace: Modelspace,
        symbols: SymbolBlockFactory,
        rejection: PlantExplanation,
    ) -> str:
        layer = self._layer(document, (self._settings.rejected_layer_stem,), self._settings.rejected_color)
        insert = modelspace.add_blockref(
            symbols.rejection_block(), (rejection.x, rejection.y), dxfattribs={"layer": layer}
        )
        self._attach_identity(insert, rejection, layer)
        return layer

    def _attach_identity(self, insert: Insert, explanation: PlantExplanation, layer: str) -> None:
        insert.add_auto_attribs({self._settings.id_attribute_tag: explanation.plant_id})
        for attribute in insert.attribs:
            attribute.dxf.layer = layer
        insert.set_xdata(self._settings.xdata_application, self._xdata(explanation))

    def _xdata(self, explanation: PlantExplanation) -> list[tuple[int, str | float]]:
        primary = explanation.clearances[0] if explanation.clearances else None
        strings = (
            explanation.plant_id,
            explanation.status,
            explanation.plant_type,
            explanation.species.key if explanation.species else "",
            explanation.primary_reason_code or (primary.rule_id if primary else ""),
            _norm_summary(primary),
        )
        tags: list[tuple[int, str | float]] = [(XDATA_STRING_CODE, self._fitted(text)) for text in strings]
        tags.append((XDATA_REAL_CODE, explanation.crown_diameter_m))
        return tags

    def _fitted(self, text: str) -> str:
        encoded = (text or XDATA_EMPTY_VALUE).encode("utf-8")[: self._settings.xdata_max_bytes]
        return encoded.decode("utf-8", errors="ignore")

    def _write_zones(
        self, document: Drawing, modelspace: Modelspace, site: SiteModel, zones: PlantingZones
    ) -> Counter[str]:
        settings = self._settings
        plantable = site.plantable_surface
        areas = (
            (
                settings.zone_restricted_layer_stem,
                settings.zone_restricted_color,
                plantable.intersection(zones.prohibited),
            ),
            (
                settings.zone_conditional_layer_stem,
                settings.zone_conditional_color,
                plantable.intersection(zones.conditional).difference(zones.prohibited),
            ),
            (
                settings.zone_allowed_layer_stem,
                settings.zone_allowed_color,
                plantable.difference(zones.prohibited).difference(zones.conditional),
            ),
        )
        counts: Counter[str] = Counter()
        for stem, color, area in areas:
            layer = self._layer(document, (stem,), color)
            counts[layer] += self._write_outlines(modelspace, area, layer)
        return counts

    def _write_shrub_groups(
        self, document: Drawing, modelspace: Modelspace, report: PlantingReport
    ) -> Counter[str]:
        settings = self._settings
        positions = [(plant.x, plant.y) for plant in report.plants if plant.plant_type == SHRUB]
        areas = shrub_group_areas(
            positions,
            settings.shrub_group_radius_m,
            settings.shrub_group_min_size,
            settings.shrub_group_simplify_m,
        )
        if not areas:
            return Counter()
        layer = self._layer(document, (settings.shrub_group_layer_stem,), settings.shrub_group_color)
        written = 0
        for area in areas:
            written += self._write_outlines(modelspace, area, layer)
            self._write_hatch(modelspace, area, layer)
            written += 1
        return Counter({layer: written})

    def _write_hatch(self, modelspace: Modelspace, area: BaseGeometry, layer: str) -> None:
        settings = self._settings
        for polygon in polygonal_parts(area):
            hatch = modelspace.add_hatch(color=settings.shrub_group_color, dxfattribs={"layer": layer})
            hatch.set_pattern_fill(settings.shrub_group_hatch_pattern, scale=settings.shrub_group_hatch_scale)
            hatch.paths.add_polyline_path(
                list(polygon.exterior.coords)[:-1], is_closed=True, flags=const.BOUNDARY_PATH_EXTERNAL
            )
            for interior in polygon.interiors:
                hatch.paths.add_polyline_path(list(interior.coords)[:-1], is_closed=True)

    def _write_outlines(self, modelspace: Modelspace, area: BaseGeometry, layer: str) -> int:
        written = 0
        for polygon in polygonal_parts(area):
            for ring in (polygon.exterior, *polygon.interiors):
                points = [(coordinate[0], coordinate[1]) for coordinate in ring.coords[:-1]]
                modelspace.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
                written += 1
        return written

    def _write_meta(
        self,
        document: Drawing,
        modelspace: Modelspace,
        site: SiteModel,
        report: PlantingReport,
        generated_at: str,
    ) -> str:
        settings = self._settings
        layer = self._layer(document, (settings.meta_layer_stem,), settings.meta_color)
        summary = report.summary
        lines = (
            f"GreenPlan {report.engine_version}",
            report.title,
            f"Сформировано: {generated_at}",
            f"Деревьев: {summary.trees}; кустарников: {summary.shrubs}; "
            f"условно: {summary.conditional}; отказов: {summary.rejected}",
            f"Корнезащита: {format_number(summary.root_barrier_length_m)} м",
            f"Слои результата: {settings.layer_prefix}{SEPARATOR}*",
        )
        min_x, _min_y, _max_x, max_y = (
            site.boundary.bounds if not site.boundary.is_empty else (0.0, 0.0, 0.0, 0.0)
        )
        modelspace.add_mtext(
            MTEXT_PARAGRAPH.join(lines),
            dxfattribs={
                "layer": layer,
                "char_height": settings.label_height_m * META_TEXT_HEIGHT_FACTOR,
                "insert": (min_x, max_y + settings.label_height_m * META_OFFSET_FACTOR),
            },
        )
        return layer


def _norm_summary(clearance: ClearanceView | None) -> str:
    if clearance is None:
        return ""
    citations = "; ".join(citation.text_ru for citation in clearance.citations)
    actual = format_number(clearance.actual_m)
    required = format_number(clearance.required_m)
    return f"{clearance.rule_id}: {actual} / {required} м; {citations}"
