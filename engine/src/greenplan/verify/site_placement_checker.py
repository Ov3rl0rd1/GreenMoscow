from collections.abc import Sequence

from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from shapely.strtree import STRtree

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.domain.decisions import (
    OUTSIDE_PLANTABLE_SURFACE,
    OUTSIDE_SITE_BOUNDARY,
    TOO_CLOSE_TO_EXISTING_TREE,
    TOO_CLOSE_TO_PLANNED_PLANT,
)
from greenplan.domain.norms import TREE
from greenplan.domain.site import SiteModel
from greenplan.verify.verification_model import (
    DESIGN_SEVERITY,
    SITE_SEVERITY,
    SPACING_VIOLATED,
    PlacedPlant,
    VerificationViolation,
)

MEASUREMENT_DECIMALS = 3


class SitePlacementChecker:
    def __init__(
        self,
        design: DesignConstraints,
        tree_spacing_m: float,
        shrub_spacing_m: float,
        shrub_to_tree_clearance_m: float,
        tolerance_m: float,
    ) -> None:
        self._design = design
        self._spacing_by_type = {TREE: tree_spacing_m}
        self._shrub_spacing_m = shrub_spacing_m
        self._shrub_to_tree_clearance_m = shrub_to_tree_clearance_m
        self._tolerance_m = tolerance_m

    def violations(self, plants: Sequence[PlacedPlant], site: SiteModel) -> list[VerificationViolation]:
        return [
            *self._surface_violations(plants, site),
            *self._existing_tree_violations(plants, site),
            *self._spacing_violations(plants),
            *self._shrub_to_tree_violations(plants),
        ]

    def _surface_violations(
        self, plants: Sequence[PlacedPlant], site: SiteModel
    ) -> list[VerificationViolation]:
        checks = [(site.boundary, OUTSIDE_SITE_BOUNDARY)]
        if self._design.require_plantable_surface:
            checks.append((site.plantable_surface, OUTSIDE_PLANTABLE_SURFACE))
        violations: list[VerificationViolation] = []
        for area, code in checks:
            prepared = prep(area)
            violations.extend(
                VerificationViolation(plant.plant_id, code, SITE_SEVERITY)
                for plant in plants
                if not self._covers(prepared, area, plant)
            )
        return violations

    def _covers(self, prepared, area: BaseGeometry, plant: PlacedPlant) -> bool:
        return prepared.contains(plant.position) or area.distance(plant.position) <= self._tolerance_m

    def _existing_tree_violations(
        self, plants: Sequence[PlacedPlant], site: SiteModel
    ) -> list[VerificationViolation]:
        kept = [tree.position for tree in site.kept_trees()]
        if not kept:
            return []
        index = STRtree(kept)
        violations: list[VerificationViolation] = []
        for plant in plants:
            required = self._design.existing_tree_clearance_m(plant.plant_type)
            actual = plant.position.distance(kept[int(index.nearest(plant.position))])
            if actual + self._tolerance_m < required:
                violations.append(
                    self._distance_violation(plant, TOO_CLOSE_TO_EXISTING_TREE, actual, required)
                )
        return violations

    def _spacing_violations(self, plants: Sequence[PlacedPlant]) -> list[VerificationViolation]:
        violations: list[VerificationViolation] = []
        for plant_type in {plant.plant_type for plant in plants}:
            group = [plant for plant in plants if plant.plant_type == plant_type]
            spacing = self._spacing_by_type.get(plant_type, self._shrub_spacing_m)
            violations.extend(self._pairs_closer_than(group, group, spacing, SPACING_VIOLATED))
        return violations

    def _shrub_to_tree_violations(self, plants: Sequence[PlacedPlant]) -> list[VerificationViolation]:
        trees = [plant for plant in plants if plant.plant_type == TREE]
        shrubs = [plant for plant in plants if plant.plant_type != TREE]
        return self._pairs_closer_than(
            shrubs, trees, self._shrub_to_tree_clearance_m, TOO_CLOSE_TO_PLANNED_PLANT
        )

    def _pairs_closer_than(
        self,
        subjects: Sequence[PlacedPlant],
        neighbours: Sequence[PlacedPlant],
        required: float,
        code: str,
    ) -> list[VerificationViolation]:
        if not subjects or not neighbours or required <= 0:
            return []
        index = STRtree([plant.position for plant in neighbours])
        violations: list[VerificationViolation] = []
        for subject in subjects:
            limit = required - self._tolerance_m
            for found in index.query(subject.position, predicate="dwithin", distance=limit):
                neighbour = neighbours[int(found)]
                is_same_plant = neighbour.handle == subject.handle
                is_reported_from_other_side = subjects is neighbours and neighbour.plant_id > subject.plant_id
                if is_same_plant or is_reported_from_other_side:
                    continue
                actual = subject.position.distance(neighbour.position)
                if actual + self._tolerance_m < required:
                    violations.append(self._distance_violation(subject, code, actual, required))
        return violations

    def _distance_violation(
        self, plant: PlacedPlant, code: str, actual: float, required: float
    ) -> VerificationViolation:
        return VerificationViolation(
            plant.plant_id,
            code,
            DESIGN_SEVERITY,
            round(actual, MEASUREMENT_DECIMALS),
            round(required, MEASUREMENT_DECIMALS),
        )
