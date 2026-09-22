import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from greenplan.domain.site import SiteDiagnostics
from greenplan.explain.report_model import ReportSummary
from greenplan.pipeline.pipeline_request import PipelineRequest
from greenplan.pipeline.run_config import RunConfig
from greenplan.verify.verification_model import VerificationReport

RUN_SUMMARY_NAME = "run_summary.json"
TIMING_DECIMALS = 3


@dataclass(frozen=True)
class RunSummary:
    request: PipelineRequest
    config: RunConfig
    report_summary: ReportSummary
    verification: VerificationReport
    timings_s: dict[str, float]
    diagnostics: SiteDiagnostics
    output_dxf: Path
    generated_at: str
    engine_version: str
    memory_mb: dict[str, float] = field(default_factory=dict)
    peak_memory_mb: float = 0.0

    def payload(self) -> dict[str, Any]:
        summary = self.report_summary
        return {
            "engine_version": self.engine_version,
            "generated_at": self.generated_at,
            "title": self.request.title,
            "input": str(self.request.input_path),
            "overlays": [str(path) for path in self.request.overlay_paths],
            "output_dxf": str(self.output_dxf),
            "timings_s": self.timings_s,
            "total_s": round(sum(self.timings_s.values()), TIMING_DECIMALS),
            "memory_mb": self.memory_mb,
            "peak_memory_mb": self.peak_memory_mb,
            "plants": {
                "trees": summary.trees,
                "shrubs": summary.shrubs,
                "conditional": summary.conditional,
                "rejected": summary.rejected,
            },
            "verification": {
                "is_valid": self.verification.is_valid,
                "violations": len(self.verification.violations),
                "integrity_is_intact": self.verification.integrity.is_intact,
            },
            "site": asdict(self.diagnostics),
            "config": asdict(self.config),
        }

    def write(self, directory: Path) -> Path:
        path = directory / RUN_SUMMARY_NAME
        path.write_text(
            json.dumps(self.payload(), ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        return path
