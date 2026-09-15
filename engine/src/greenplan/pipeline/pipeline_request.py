from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    input_path: Path
    output_directory: Path
    title: str
    search_root: Path | None = None
    generated_at: str | None = None
