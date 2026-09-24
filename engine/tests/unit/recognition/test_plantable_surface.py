from shapely.geometry import Polygon, box

from greenplan.recognition.site_boundary_extractor import (
    CONTENT_EXTENT_SOURCE,
    WORK_BOUNDARY_SOURCE,
    SiteBoundary,
)
from greenplan.recognition.site_model_builder import plantable_surface
from greenplan.recognition.surface_classifier import NO_LAWN_SOURCE, PROJECT_SURFACES_SOURCE, SurfaceMap


def surfaces(lawn: Polygon) -> SurfaceMap:
    source = NO_LAWN_SOURCE if lawn.is_empty else PROJECT_SURFACES_SOURCE
    return SurfaceMap(lawn, Polygon(), Polygon(), source)


def test_lawn_is_clipped_by_the_work_boundary() -> None:
    area = plantable_surface(
        surfaces(box(0, 0, 20, 10)), SiteBoundary(box(10, 0, 30, 10), WORK_BOUNDARY_SOURCE)
    )
    assert area.equals(box(10, 0, 20, 10))


def test_work_boundary_is_planted_when_the_drawing_has_no_lawn() -> None:
    boundary = box(0, 0, 30, 10)
    assert plantable_surface(surfaces(Polygon()), SiteBoundary(boundary, WORK_BOUNDARY_SOURCE)).equals(
        boundary
    )


def test_drawing_extent_is_never_planted_as_a_whole() -> None:
    extent = SiteBoundary(box(0, 0, 2000, 15000), CONTENT_EXTENT_SOURCE)
    assert plantable_surface(surfaces(Polygon()), extent).is_empty
