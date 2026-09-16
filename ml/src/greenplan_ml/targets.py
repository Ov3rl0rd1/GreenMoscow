from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from greenplan.domain.norms import SHRUB, TREE
from greenplan.knowledge.plant_catalog import PlantCatalog
from greenplan.placement.raster import RasterGrid
from greenplan_ml.feature_channels import cell_indices
from greenplan_ml.reference_extractor import ReferencePlanting

TARGET_CHANNELS = ("tree_heatmap", "shrub_heatmap", "crown_diameter")
TARGET_CHANNEL_COUNT = len(TARGET_CHANNELS)
TREE_CHANNEL_INDEX = 0
SHRUB_CHANNEL_INDEX = 1
CROWN_CHANNEL_INDEX = 2
WEIGHT_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class TargetSettings:
    tree_sigma_m: float = 1.5
    shrub_sigma_m: float = 0.8
    default_tree_crown_m: float = 5.0
    default_shrub_crown_m: float = 1.5
    crown_saturation_m: float = 12.0


class SpeciesCrownLookup:
    def __init__(self, catalog: PlantCatalog, settings: TargetSettings) -> None:
        self._settings = settings
        self._crowns = {normalized_species(item.name_ru): item.crown_diameter_m for item in catalog.species()}

    @classmethod
    def from_knowledge(
        cls, knowledge_root: Path, settings: TargetSettings | None = None
    ) -> "SpeciesCrownLookup":
        catalog = PlantCatalog.from_file(knowledge_root / "plants" / "assortment.yaml")
        return cls(catalog, settings or TargetSettings())

    def crown_for(self, target: str, species_ru: str) -> float:
        name = normalized_species(species_ru)
        known = self._crowns.get(name) or self._by_prefix(name)
        if known is not None:
            return known
        return self._settings.default_tree_crown_m if target == TREE else self._settings.default_shrub_crown_m

    def _by_prefix(self, name: str) -> float | None:
        if not name:
            return None
        matches = [
            crown
            for known, crown in self._crowns.items()
            if name.startswith(known) or known.startswith(name)
        ]
        return max(matches) if matches else None


class TargetStackBuilder:
    def __init__(self, crowns: SpeciesCrownLookup, settings: TargetSettings | None = None) -> None:
        self._crowns = crowns
        self._settings = settings or TargetSettings()

    def build(self, grid: RasterGrid, plantings: Sequence[ReferencePlanting]) -> np.ndarray:
        targets = np.zeros((TARGET_CHANNEL_COUNT, *grid.shape), dtype=np.float32)
        weights = np.zeros(grid.shape, dtype=np.float32)
        crown_sum = np.zeros(grid.shape, dtype=np.float32)
        for target, channel, sigma_m in self._channel_plan():
            selected = [planting for planting in plantings if planting.target == target]
            heat, crowns = self._heat_and_crowns(grid, selected, sigma_m)
            targets[channel] = np.clip(heat, 0.0, 1.0)
            weights += heat
            crown_sum += crowns
        targets[CROWN_CHANNEL_INDEX] = self._crown_channel(crown_sum, weights)
        return targets

    def _channel_plan(self) -> tuple[tuple[str, int, float], ...]:
        return (
            (TREE, TREE_CHANNEL_INDEX, self._settings.tree_sigma_m),
            (SHRUB, SHRUB_CHANNEL_INDEX, self._settings.shrub_sigma_m),
        )

    def _heat_and_crowns(
        self, grid: RasterGrid, plantings: Sequence[ReferencePlanting], sigma_m: float
    ) -> tuple[np.ndarray, np.ndarray]:
        impulses = np.zeros(grid.shape, dtype=np.float32)
        crowns = np.zeros(grid.shape, dtype=np.float32)
        positions = [[planting.position.x, planting.position.y] for planting in plantings]
        coordinates = np.array(positions, dtype=float)
        empty = (np.empty(0, dtype=int), np.empty(0, dtype=int))
        rows, columns = cell_indices(grid, coordinates) if coordinates.size else empty
        for index, (row, column) in enumerate(zip(rows, columns, strict=True)):
            planting = plantings[index]
            impulses[row, column] += 1.0
            crowns[row, column] += self._crowns.crown_for(planting.target, planting.species_ru)
        return splat(impulses, sigma_m / grid.cell_size_m), splat(crowns, sigma_m / grid.cell_size_m)

    def _crown_channel(self, crown_sum: np.ndarray, weights: np.ndarray) -> np.ndarray:
        average = crown_sum / np.maximum(weights, WEIGHT_EPSILON)
        return np.clip(average / self._settings.crown_saturation_m, 0.0, 1.0).astype(np.float32)


def splat(impulses: np.ndarray, sigma_cells: float) -> np.ndarray:
    if not impulses.any():
        return impulses
    filtered = gaussian_filter(impulses, sigma_cells, mode="constant")
    return (filtered * (2.0 * np.pi * sigma_cells**2)).astype(np.float32)


def normalized_species(name: str) -> str:
    return " ".join(name.lower().replace("ё", "е").replace("'", " ").split())


def planting_counts(plantings: Sequence[ReferencePlanting]) -> Mapping[str, int]:
    return {
        TREE: sum(1 for planting in plantings if planting.target == TREE),
        SHRUB: sum(1 for planting in plantings if planting.target == SHRUB),
    }
