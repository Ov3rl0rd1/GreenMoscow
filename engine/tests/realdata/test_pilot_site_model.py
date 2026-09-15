import pytest

from greenplan.domain.site import SiteModel

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


def test_underground_networks_are_recognized(bagritskogo_site: SiteModel) -> None:
    counts = bagritskogo_site.diagnostics.obstacle_counts
    for kind in (
        "gas_pipeline",
        "water_supply",
        "sewer",
        "heating_network",
        "power_cable",
        "communication_cable",
    ):
        assert counts.get(kind, 0) > 0, kind


def annotated_length_share(site: SiteModel, kind: str) -> float:
    runs = site.obstacles_of(kind)
    annotated = sum(run.geometry.length for run in runs if run.outer_radius_m is not None)
    return annotated / sum(run.geometry.length for run in runs)


def test_pipelines_get_diameter_from_annotations(bagritskogo_site: SiteModel) -> None:
    assert bagritskogo_site.diagnostics.annotated_network_share > 0.2
    for kind, minimum_share in (("gas_pipeline", 0.4), ("water_supply", 0.35), ("sewer", 0.4)):
        assert annotated_length_share(bagritskogo_site, kind) > minimum_share, kind


def test_boundary_and_lawns_come_from_project_layers(bagritskogo_site: SiteModel) -> None:
    diagnostics = bagritskogo_site.diagnostics
    assert diagnostics.boundary_source == "work_boundary"
    assert diagnostics.lawn_source == "project_surfaces"
    assert bagritskogo_site.boundary.area > 5_000
    assert 500 < bagritskogo_site.plantable_surface.area < bagritskogo_site.boundary.area


def test_existing_trees_are_found(bagritskogo_site: SiteModel) -> None:
    assert len(bagritskogo_site.kept_trees()) > 100


def test_carriageway_edges_and_lamps_are_present(bagritskogo_site: SiteModel) -> None:
    counts = bagritskogo_site.diagnostics.obstacle_counts
    assert counts.get("carriageway_edge", 0) > 0
    assert counts.get("lighting_pole", 0) > 0
