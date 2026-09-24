import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

TIMING_DECIMALS = 3
MEMORY_DECIMALS = 1
BYTES_IN_MEGABYTE = 1024 * 1024

StageListener = Callable[[str], None]


def ignore_stage(name: str) -> None:
    return None


def process_memory_mb() -> float:
    try:
        import psutil
    except ImportError:
        return 0.0
    return psutil.Process().memory_info().rss / BYTES_IN_MEGABYTE


class StageTimer:
    def __init__(self, listener: StageListener = ignore_stage) -> None:
        self.durations: dict[str, float] = {}
        self.memory_mb: dict[str, float] = {}
        self.peak_memory_mb: float = round(process_memory_mb(), MEMORY_DECIMALS)
        self._listener = listener

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        self._listener(name)
        started = time.perf_counter()
        try:
            yield
        finally:
            self.durations[name] = round(time.perf_counter() - started, TIMING_DECIMALS)
            self._remember_memory(name)

    def _remember_memory(self, name: str) -> None:
        used = round(process_memory_mb(), MEMORY_DECIMALS)
        self.memory_mb[name] = used
        self.peak_memory_mb = max(self.peak_memory_mb, used)
