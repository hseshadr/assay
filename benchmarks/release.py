"""Run isolated scoring-only Python release benchmarks."""

from __future__ import annotations

import json
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
    BENCHMARK_BUDGETS_MS,
    BINARY_BOOTSTRAP_RESAMPLES,
    BINARY_ITEM_COUNT,
    COMPOSITION_BATCH_COUNT,
    HEAVY_SAMPLES,
    MINIMUM_COMPONENT_COUNT,
    BenchmarkReport,
    exact_sha,
    peak_rss_mib,
    percentile,
    require_budget,
    toolchain,
)

_CHILD_ARGUMENT_COUNT = 3
_TIMEOUT_MARGIN_SECONDS = 15.0


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


def _timing(operation: Callable[[], object]) -> float:
    started = time.perf_counter()
    operation()
    return (time.perf_counter() - started) * 1_000.0


def _report(
    workload: str, count: int, timings: tuple[float, ...], peaks: tuple[float, ...]
) -> BenchmarkReport:
    python, system = toolchain()
    p50, p95, p99 = (percentile(timings, value) for value in (0.50, 0.95, 0.99))
    return BenchmarkReport(
        workload=workload,
        count=count,
        samples=len(timings),
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        peak_rss_mib=max(peaks),
        python=python,
        platform=system,
        sha=exact_sha(),
    )


def _composition_batch() -> tuple[int, Callable[[], object]]:
    request = _small_request()

    def run() -> None:
        for _ in range(COMPOSITION_BATCH_COUNT):
            compose(request)

    return COMPOSITION_BATCH_COUNT, run


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


def _minimum_compose_replay() -> tuple[int, Callable[[], object]]:
    request = _minimum_request()

    def run() -> None:
        result = compose(request)
        ScoreResult.model_validate_json(result.model_dump_json(by_alias=True))

    return MINIMUM_COMPONENT_COUNT, run


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


def _binary_measurement() -> tuple[int, Callable[[], object]]:
    request = _binary_request()
    return BINARY_ITEM_COUNT, lambda: measure(request)


_RUNNERS: dict[str, Callable[[], tuple[int, Callable[[], object]]]] = {
    "composition": _composition_batch,
    "minimum": _minimum_compose_replay,
    "binary": _binary_measurement,
}

_WORKLOADS = {
    "composition": "python-composition-batch",
    "minimum": "python-minimum-compose-replay",
    "binary": "python-binary-measurement",
}
_COUNTS = {
    "composition": COMPOSITION_BATCH_COUNT,
    "minimum": MINIMUM_COMPONENT_COUNT,
    "binary": BINARY_ITEM_COUNT,
}


def _sample_timeout(name: str) -> float:
    budget = BENCHMARK_BUDGETS_MS[_WORKLOADS[name]] / 1_000.0
    return budget + _TIMEOUT_MARGIN_SECONDS


def _run_sample(name: str) -> tuple[float, float]:
    try:
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "benchmarks.release", "--sample", name],
            check=True,
            capture_output=True,
            text=True,
            timeout=_sample_timeout(name),
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("benchmark child timed out") from error
    payload = json.loads(completed.stdout)
    return float(payload["elapsed_ms"]), float(payload["peak_rss_mib"])


def _isolated_report(name: str) -> BenchmarkReport:
    samples = tuple(_run_sample(name) for _ in range(HEAVY_SAMPLES))
    timings = tuple(sample[0] for sample in samples)
    peaks = tuple(sample[1] for sample in samples)
    return _report(_WORKLOADS[name], _COUNTS[name], timings, peaks)


def _run_one_sample(name: str) -> None:
    _count, operation = _RUNNERS[name]()
    payload = {"elapsed_ms": _timing(operation), "peak_rss_mib": peak_rss_mib()}
    print(json.dumps(payload, separators=(",", ":")))


def _run_all() -> None:
    for name in _RUNNERS:
        report = _isolated_report(name)
        require_budget(report)
        print(report.model_dump_json())


def main() -> None:
    if len(sys.argv) == _CHILD_ARGUMENT_COUNT and sys.argv[1] == "--sample":
        _run_one_sample(sys.argv[2])
        return
    if len(sys.argv) == _CHILD_ARGUMENT_COUNT and sys.argv[1] == "--workload":
        report = _isolated_report(sys.argv[2])
        require_budget(report)
        print(report.model_dump_json())
        return
    _run_all()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
