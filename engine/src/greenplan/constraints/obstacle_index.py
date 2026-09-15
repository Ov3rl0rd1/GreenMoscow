from collections.abc import Sequence

from shapely.geometry import Point
from shapely.strtree import STRtree

from greenplan.domain.site import Obstacle


class ObstacleIndex:
    def __init__(self, obstacles: Sequence[Obstacle]) -> None:
        self._obstacles = tuple(obstacles)
        self._tree = STRtree([obstacle.geometry for obstacle in self._obstacles]) if self._obstacles else None

    def within(self, position: Point, radius_m: float) -> tuple[Obstacle, ...]:
        if self._tree is None:
            return ()
        indices = self._tree.query(position, predicate="dwithin", distance=radius_m)
        return tuple(self._obstacles[int(index)] for index in sorted(indices))

    def all(self) -> tuple[Obstacle, ...]:
        return self._obstacles
