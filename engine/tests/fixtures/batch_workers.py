import os

from greenplan.domain.errors import DrawingLoadError
from greenplan.explain.report_model import ReportSummary
from greenplan.pipeline.planning_pipeline import PipelineResult
from greenplan.verify.verification_model import IntegrityReport, VerificationReport

CRASH_EXIT_CODE = 3


def summary() -> ReportSummary:
    return ReportSummary(
        trees=12,
        shrubs=30,
        conditional=2,
        rejected=5,
        species=(),
        plantable_area_m2=1000.0,
        tree_allowed_area_m2=500.0,
        max_trees=20,
        max_shrubs=60,
        tree_spacing_m=6.0,
        shrub_spacing_m=1.0,
        boundary_source="граница работ",
        lawn_source="газоны",
        annotated_network_share=0.5,
        unresolved_references=(),
    )


def verification() -> VerificationReport:
    return VerificationReport(
        output_path="out.dxf",
        plants_checked=42,
        violations=(),
        integrity=IntegrityReport((), (), (), ()),
    )


class FakePipeline:
    def __init__(self, failing: set[str]) -> None:
        self._failing = failing
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        if request.title in self._failing:
            raise DrawingLoadError(f"не открывается {request.input_path.name}")
        return PipelineResult(
            output_dxf=request.output_directory / "result.dxf",
            artifacts={},
            report_summary=summary(),
            verification=verification(),
            timings_s={"read_drawings": 10.0, "place_plants": 5.0},
            diagnostics=None,
            memory_mb={"read_drawings": 900.0},
            peak_memory_mb=1200.0,
        )


def fake_pipeline() -> FakePipeline:
    return FakePipeline(failing={"Вторая улица"})


class CrashingPipeline(FakePipeline):
    def run(self, request):
        if request.title == "Первая улица":
            os._exit(CRASH_EXIT_CODE)
        return super().run(request)


def crashing_pipeline() -> CrashingPipeline:
    return CrashingPipeline(failing=set())
