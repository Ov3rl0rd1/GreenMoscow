import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely

from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteModel
from greenplan.knowledge.pilot_objects import PilotCatalog, PilotObject
from greenplan_ml.feature_channels import (
    CHANNEL_NAMES,
    PLANTABLE_CHANNEL_INDEX,
    FeatureSettings,
    FeatureStackBuilder,
)
from greenplan_ml.reference_extractor import ReferencePlanting, ReferencePlantingExtractor
from greenplan_ml.sample_builder import SampleSettings, channel_pad_values, pad_to_size, plan_crops
from greenplan_ml.sample_store import (
    GridMeta,
    ObjectMeta,
    PlantingMeta,
    ScaleMeta,
    masks_of,
    write_object,
)
from greenplan_ml.site_loader import SiteLoader
from greenplan_ml.targets import TARGET_CHANNELS, SpeciesCrownLookup, TargetSettings, TargetStackBuilder

MANIFEST_FILE = "dataset.json"
NO_PLANTINGS_REASON = "no_reference_plantings"
MISALIGNED_REASON = "reference_outside_site_boundary"
EMPTY_SITE_REASON = "empty_plantable_surface"


@dataclass(frozen=True, slots=True)
class ObjectReport:
    object_id: str
    level: str
    is_built: bool
    reason: str = ""
    crops: int = 0
    trees: int = 0
    shrubs: int = 0
    inside_boundary_share: float = 0.0
    scheme_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "level": self.level,
            "is_built": self.is_built,
            "reason": self.reason,
            "crops": self.crops,
            "trees": self.trees,
            "shrubs": self.shrubs,
            "inside_boundary_share": round(self.inside_boundary_share, 3),
            "scheme_id": self.scheme_id,
        }


class DatasetBuilder:
    def __init__(
        self,
        loader: SiteLoader,
        extractor: ReferencePlantingExtractor,
        features: FeatureStackBuilder,
        targets: TargetStackBuilder,
        samples: SampleSettings,
        scales: ScaleMeta,
        minimum_inside_share: float = 0.5,
    ) -> None:
        self._loader = loader
        self._extractor = extractor
        self._features = features
        self._targets = targets
        self._samples = samples
        self._scales = scales
        self._minimum_inside_share = minimum_inside_share

    @classmethod
    def from_knowledge(
        cls,
        knowledge_root: Path,
        dwg2dxf: Path | None = None,
        cache_directory: Path | None = None,
        features: FeatureSettings | None = None,
        targets: TargetSettings | None = None,
        samples: SampleSettings | None = None,
    ) -> "DatasetBuilder":
        target_settings = targets or TargetSettings()
        feature_settings = features or FeatureSettings()
        return cls(
            loader=SiteLoader.from_knowledge(
                knowledge_root, dwg2dxf, cache_directory, feature_settings.cell_size_m
            ),
            extractor=ReferencePlantingExtractor.from_knowledge(knowledge_root),
            features=FeatureStackBuilder(feature_settings),
            targets=TargetStackBuilder(
                SpeciesCrownLookup.from_knowledge(knowledge_root, target_settings), target_settings
            ),
            samples=samples or SampleSettings(),
            scales=ScaleMeta(
                clearance_saturation_m=feature_settings.clearance_saturation_m,
                max_distance_m=feature_settings.max_distance_m,
                crown_saturation_m=target_settings.crown_saturation_m,
            ),
        )

    def build_object(self, item: PilotObject, dataset_root: Path, output_root: Path) -> ObjectReport:
        input_path = dataset_root / item.input_path
        loaded = self._loader.load(input_path, dataset_root / item.input_path.split("/")[0])
        if loaded.site.plantable_surface.is_empty:
            return ObjectReport(item.object_id, item.level, False, EMPTY_SITE_REASON)
        content = self._loader.read(dataset_root / item.reference_path)
        plantings = self._extractor.extract(content, item.layer_scheme)
        if not plantings.plantings:
            return ObjectReport(item.object_id, item.level, False, NO_PLANTINGS_REASON)
        share = inside_share(loaded.site, plantings.plantings)
        if share < self._minimum_inside_share:
            return ObjectReport(
                item.object_id, item.level, False, MISALIGNED_REASON, inside_boundary_share=share
            )
        return self._store(item, loaded, plantings, share, output_root / item.object_id)

    def build_all(
        self,
        catalog: PilotCatalog,
        dataset_root: Path,
        output_root: Path,
        levels: Sequence[str] | None,
        object_ids: Sequence[str] | None = None,
    ) -> list[ObjectReport]:
        reports = [
            self.build_object(item, dataset_root, output_root)
            for item in catalog.selected(levels, object_ids)
        ]
        write_manifest(output_root, reports, self._samples)
        return reports

    def _store(self, item, loaded, plantings, share: float, directory: Path) -> ObjectReport:
        stack = self._features.build_from_raster(loaded.site, loaded.raster)
        targets = self._targets.build(stack.grid, plantings.plantings)
        size = self._samples.crop_size
        features = pad_to_size(stack.channels, size, channel_pad_values(stack.names))
        padded_targets = pad_to_size(targets, size, np.zeros(targets.shape[0], dtype=np.float32))
        masks = masks_of(loaded.raster)
        padded_masks = pad_to_size(masks, size, np.zeros(masks.shape[0], dtype=np.float32))
        windows = plan_crops(features[PLANTABLE_CHANNEL_INDEX], self._samples)
        counts = {
            TREE: len(plantings.of_target(TREE)),
            SHRUB: len(plantings.of_target(SHRUB)),
        }
        meta = ObjectMeta(
            object_id=item.object_id,
            level=item.level,
            grid=GridMeta.of(stack.grid),
            channels=stack.names,
            target_channels=TARGET_CHANNELS,
            crop_size=size,
            crops=tuple(windows),
            tree_count=counts[TREE],
            shrub_count=counts[SHRUB],
            inside_boundary_share=round(share, 4),
            scheme_id=plantings.scheme_id,
            scales=self._scales,
            plantings=tuple(_planting_meta(planting) for planting in plantings.plantings),
        )
        write_object(directory, features, padded_targets, padded_masks, meta)
        return ObjectReport(
            object_id=item.object_id,
            level=item.level,
            is_built=True,
            crops=len(windows),
            trees=counts[TREE],
            shrubs=counts[SHRUB],
            inside_boundary_share=share,
            scheme_id=plantings.scheme_id,
        )


def inside_share(site: SiteModel, plantings: Sequence[ReferencePlanting]) -> float:
    counted = [planting for planting in plantings if not planting.from_area] or list(plantings)
    if not counted or site.boundary.is_empty:
        return 0.0
    shapely.prepare(site.boundary)
    xs = np.array([planting.position.x for planting in counted], dtype=float)
    ys = np.array([planting.position.y for planting in counted], dtype=float)
    return float(shapely.contains_xy(site.boundary, xs, ys).mean())


def write_manifest(output_root: Path, reports: Sequence[ObjectReport], samples: SampleSettings) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / MANIFEST_FILE
    payload = {
        "crop_size": samples.crop_size,
        "stride": samples.stride,
        "channels": list(CHANNEL_NAMES),
        "target_channels": list(TARGET_CHANNELS),
        "objects": merged_objects(path, reports),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def merged_objects(path: Path, reports: Sequence[ObjectReport]) -> list[dict[str, Any]]:
    rebuilt = {report.object_id for report in reports}
    kept = [item for item in existing_objects(path) if item.get("object_id") not in rebuilt]
    return kept + [report.as_dict() for report in reports]


def existing_objects(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    content = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in content.get("objects", []) if isinstance(item, dict)]


def _planting_meta(planting: ReferencePlanting) -> PlantingMeta:
    return PlantingMeta(
        x=round(planting.position.x, 3),
        y=round(planting.position.y, 3),
        target=planting.target,
        species_ru=planting.species_ru,
    )
