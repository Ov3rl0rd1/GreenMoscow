import time

from greenplan.pipeline.stage_timer import StageTimer, process_memory_mb


def test_stage_records_duration_and_memory() -> None:
    timer = StageTimer()
    with timer.stage("read"):
        time.sleep(0.01)
    assert timer.durations["read"] >= 0.01
    assert timer.memory_mb["read"] > 0
    assert timer.peak_memory_mb >= timer.memory_mb["read"]


def test_peak_keeps_the_largest_stage() -> None:
    timer = StageTimer()
    with timer.stage("small"):
        pass
    timer.memory_mb["small"] = 10.0
    timer.peak_memory_mb = 10.0
    with timer.stage("large"):
        blocks = [bytearray(2 * 1024 * 1024) for _ in range(8)]
        assert len(blocks) == 8
    assert timer.peak_memory_mb >= timer.memory_mb["large"]
    assert timer.peak_memory_mb >= 10.0


def test_memory_reading_is_available() -> None:
    assert process_memory_mb() > 0
