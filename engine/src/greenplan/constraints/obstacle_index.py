from collections.abc import Sequence

from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from greenplan.domain.site import Obstacle


class ObstacleIndex:
    def __init__(self, obstacles: Sequence[Obstacle]) -> None:
        self._obstacles = tuple(obstacles)
        self._tree = STRtree([obstacle.geometry for obstacle in self._obstacles]) if self._obstacles else None

    def within(self, geometry: BaseGeometry, radius_m: float) -> tuple[Obstacle, ...]:
        if self._tree is None or geometry.is_empty:
            return ()
        indices = self._tree.query(geometry, predicate="dwithin", distance=radius_m)
        return tuple(self._obstacles[int(index)] for index in sorted(indices))

    def all(self) -> tuple[Obstacle, ...]:
        return self._obstacles
