import re
from dataclasses import dataclass
from pathlib import Path

from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

MILLIMETERS_IN_METER = 1000.0


@dataclass(frozen=True, slots=True)
class NetworkAnnotation:
    text: str
    pipe_diameter_mm: float | None
    pipe_count: int
    channel_width_mm: float | None
    casing_diameter_mm: float | None
    casing_count: int = 1

    @property
    def outer_width_m(self) -> float | None:
        if self.channel_width_mm is not None:
            return self.channel_width_mm / MILLIMETERS_IN_METER
        if self.casing_diameter_mm is not None:
            return self.casing_count * self.casing_diameter_mm / MILLIMETERS_IN_METER
        if self.pipe_diameter_mm is not None:
            return self.pipe_count * self.pipe_diameter_mm / MILLIMETERS_IN_METER
        return None


class NetworkAnnotationParser:
    def __init__(
        self,
        diameter_pattern: re.Pattern[str],
        channel_pattern: re.Pattern[str],
        casing_pattern: re.Pattern[str],
    ) -> None:
        self._diameter_pattern = diameter_pattern
        self._channel_pattern = channel_pattern
        self._casing_pattern = casing_pattern

    @classmethod
    def from_file(cls, path: Path) -> "NetworkAnnotationParser":
        patterns = require_key(load_yaml_mapping(path), "meta", path)["annotation_regex"]
        return cls(
            re.compile(patterns["diameter_mm"]),
            re.compile(patterns["channel_section_mm"]),
            re.compile(patterns["casing_diameter_mm"]),
        )

    def parse(self, text: str) -> NetworkAnnotation | None:
        casing = self._casing_pattern.search(text)
        text_without_casing = self._casing_pattern.sub("", text)
        diameter = self._diameter_pattern.search(text_without_casing)
        channel = self._channel_section(text_without_casing)
        if diameter is None and casing is None and channel is None:
            return None
        pipe_count, pipe_diameter = _count_and_diameter(diameter)
        casing_count, casing_diameter = _count_and_diameter(casing)
        return NetworkAnnotation(text, pipe_diameter, pipe_count, channel, casing_diameter, casing_count)

    def _channel_section(self, text: str) -> float | None:
        without_diameter = self._diameter_pattern.sub("", text)
        channel = self._channel_pattern.search(without_diameter)
        return float(channel.group(1)) if channel else None


def _count_and_diameter(match: re.Match[str] | None) -> tuple[int, float | None]:
    if match is None:
        return 1, None
    count = int(match.group(1)) if match.group(1) else 1
    return count, float(match.group(2))
