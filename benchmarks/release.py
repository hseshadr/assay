"""Run isolated scoring-only Python release benchmarks."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable

from assay import (
    BinaryMeasurementRequest,
    BinaryMetricControls,
    ClampPolicy,
    Component,
    Direction,
    MinimumRequest,
    NativeScale,
    ScoreResult,
    compose,
    measure,
)
from benchmarks._contracts import (
    BINARY_BOOTSTRAP_RESAMPLES,
    BINARY_ITEM_COUNT,
    COMPOSITION_BATCH_COUNT,
    COMPOSITION_SAMPLES,
    MINIMUM_COMPONENT_COUNT,
    BenchmarkReport,
    exact_sha,
    peak_rss_mib,
    percentile,
    require_budget,
    toolchain,
)

_CHILD_ARGUMENT_COUNT = 3


def _component(index: int, value: float) -> Component:
    scale = NativeScale(
        minimum=0.0,
        maximum=100.0,
        direction=Direction.HIGHER_IS_BETTER,
    )
    return Component(id=f"component-{index}", label=f"Component {index}", value=value, scale=scale)


def _small_request() -> MinimumRequest:
    return MinimumRequest(
        method="minimum",
        method_version="benchmark-v1",
        components=(_component(0, 60.0), _component(1, 80.0)),
        clamp=ClampPolicy.REJECT,
    )


def _timings(operation: Callable[[], object], samples: int) -> tuple[float, ...]:
    values = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1_000.0)
    return tuple(values)


def _report(workload: str, count: int, timings: tuple[float, ...]) -> BenchmarkReport:
    python, system = toolchain()
    return BenchmarkReport(
        workload=workload,
        count=count,
        p50_ms=percentile(timings, 0.50),
        p95_ms=percentile(timings, 0.95),
        p99_ms=percentile(timings, 0.99),
        peak_rss_mib=peak_rss_mib(),
        python=python,
        platform=system,
        sha=exact_sha(),
    )


def _composition_batch() -> BenchmarkReport:
    request = _small_request()

    def run() -> None:
        for _ in range(COMPOSITION_BATCH_COUNT):
            compose(request)

    timings = _timings(run, COMPOSITION_SAMPLES)
    return _report("python-composition-batch", COMPOSITION_BATCH_COUNT, timings)


def _minimum_request() -> MinimumRequest:
    components = tuple(
        _component(index, float(index % 101)) for index in range(MINIMUM_COMPONENT_COUNT)
    )
    return MinimumRequest(
        method="minimum",
        method_version="benchmark-v1",
        components=components,
        clamp=ClampPolicy.REJECT,
    )


def _minimum_compose_replay() -> BenchmarkReport:
    request = _minimum_request()

    def run() -> None:
        result = compose(request)
        ScoreResult.model_validate_json(result.model_dump_json(by_alias=True))

    timings = _timings(run, 1)
    return _report("python-minimum-compose-replay", MINIMUM_COMPONENT_COUNT, timings)


def _binary_controls() -> BinaryMetricControls:
    return BinaryMetricControls(
        min_samples=30,
        bootstrap_resamples=BINARY_BOOTSTRAP_RESAMPLES,
        confidence_level=0.95,
        ece_bins=15,
        bootstrap_seed=12345,
    )


def _binary_request() -> BinaryMeasurementRequest:
    labels = tuple(index % 2 for index in range(BINARY_ITEM_COUNT))
    scores = tuple(0.9 if label else 0.1 for label in labels)
    return BinaryMeasurementRequest(
        metric="binary",
        metric_version="benchmark-v1",
        y_true=labels,
        y_score=scores,
        threshold=0.5,
        controls=_binary_controls(),
    )


def _binary_measurement() -> BenchmarkReport:
    request = _binary_request()
    timings = _timings(lambda: measure(request), 1)
    return _report("python-binary-measurement", BINARY_ITEM_COUNT, timings)


_RUNNERS: dict[str, Callable[[], BenchmarkReport]] = {
    "composition": _composition_batch,
    "minimum": _minimum_compose_replay,
    "binary": _binary_measurement,
}


def _run_child(name: str) -> BenchmarkReport:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and internal runner key
        [sys.executable, "-m", "benchmarks.release", "--workload", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return BenchmarkReport.model_validate_json(completed.stdout)


def _run_all() -> None:
    for name in _RUNNERS:
        report = _run_child(name)
        require_budget(report)
        print(report.model_dump_json())


def main() -> None:
    if len(sys.argv) == _CHILD_ARGUMENT_COUNT and sys.argv[1] == "--workload":
        report = _RUNNERS[sys.argv[2]]()
        require_budget(report)
        print(report.model_dump_json())
        return
    _run_all()


if __name__ == "__main__":
    main()
