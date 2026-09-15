import time
from collections.abc import Iterator
from contextlib import contextmanager

TIMING_DECIMALS = 3


class StageTimer:
    def __init__(self) -> None:
        self.durations: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.durations[name] = round(time.perf_counter() - started, TIMING_DECIMALS)
