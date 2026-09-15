from shapely.geometry import LineString, Point, box

from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE, GAS_PIPELINE, LIGHTING_POLE, SIDEWALK_EDGE
from greenplan.domain.site import KEEP_TREE_STATUS, ExistingTree, Obstacle, SiteDiagnostics, SiteModel

LAWN = box(0, 10, 100, 20)
GAS_AXIS_Y = 15.0
GAS_OUTER_RADIUS_M = 0.055
POLE = Point(30, 9)
KEPT_TREE = Point(70, 18)


def street_site(with_street_axis: bool = True) -> SiteModel:
    obstacles = (
        Obstacle(CARRIAGEWAY_EDGE, box(0, 0, 100, 8).exterior, "surfaces", "surface_edges", ("surface",)),
        Obstacle(SIDEWALK_EDGE, box(0, 20, 100, 23).exterior, "surfaces", "surface_edges", ("surface",)),
        Obstacle(
            GAS_PIPELINE,
            LineString([(-10, GAS_AXIS_Y), (110, GAS_AXIS_Y)]),
            "Газопровод",
            "tile_up",
            ("layer:Газопровод",),
            GAS_OUTER_RADIUS_M,
        ),
        Obstacle(LIGHTING_POLE, POLE, "Фонари", "tile_tp", ("layer:Фонари",)),
    )
    return SiteModel(
        boundary=box(0, -2, 100, 30),
        plantable_surface=LAWN,
        obstacles=obstacles,
        existing_trees=(ExistingTree(KEPT_TREE, KEEP_TREE_STATUS, "Отдельно стоящее дерево", "tile_tp"),),
        street_axes=(LineString([(0, 4), (100, 4)]),) if with_street_axis else (),
        diagnostics=SiteDiagnostics(),
    )
