"""Typed benchmark evidence and frozen release budgets."""

from __future__ import annotations

import math
import platform
import resource
import subprocess
import sys
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

COMPOSITION_BATCH_COUNT: Final[int] = 2_000
COMPOSITION_SAMPLES: Final[int] = 5
MINIMUM_COMPONENT_COUNT: Final[int] = 150_000
BINARY_ITEM_COUNT: Final[int] = 10_000
BINARY_BOOTSTRAP_RESAMPLES: Final[int] = 99
BENCHMARK_BUDGETS_MS: Final[dict[str, float]] = {
    "python-composition-batch": 8_000.0,
    "python-minimum-compose-replay": 60_000.0,
    "python-binary-measurement": 30_000.0,
}
BENCHMARK_RSS_BUDGET_MIB: Final[dict[str, float]] = {
    "python-composition-batch": 512.0,
    "python-minimum-compose-replay": 1_536.0,
    "python-binary-measurement": 768.0,
}


class BenchmarkReport(BaseModel):
    """One workload's reproducible count, latency, memory, and toolchain evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    workload: str
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    peak_rss_mib: float
    python: str
    platform: str
    sha: str


def percentile(samples: Sequence[float], percentile_value: float) -> float:
    """Return the nearest-rank percentile for a nonempty sample."""
    ordered = sorted(samples)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def peak_rss_mib() -> float:
    """Normalize ru_maxrss to MiB on Linux and macOS."""
    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    bytes_used = raw if sys.platform == "darwin" else raw * 1024.0
    return bytes_used / (1024.0 * 1024.0)


def exact_sha() -> str:
    """Read the exact Git commit represented by this benchmark."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607 - fixed local VCS query
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def toolchain() -> tuple[str, str]:
    """Return explicit Python and platform identities."""
    python = ".".join(str(part) for part in sys.version_info[:3])
    return python, platform.platform()


def require_budget(report: BenchmarkReport) -> None:
    """Fail when latency or memory exceeds the frozen release budget."""
    if report.p99_ms > BENCHMARK_BUDGETS_MS[report.workload]:
        raise RuntimeError("benchmark latency budget exceeded")
    if report.peak_rss_mib > BENCHMARK_RSS_BUDGET_MIB[report.workload]:
        raise RuntimeError("benchmark memory budget exceeded")
