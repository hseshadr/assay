"""Uncertainty with an honesty floor.

Above ``min_samples`` we return a percentile bootstrap confidence interval
(``scipy.stats.bootstrap``, fixed seed → reproducible). Below the floor we return
an ``Abstention`` — never a point estimate the data cannot support. ``percentile``
is chosen over ``BCa`` because it is robust and fully deterministic with a fixed
seed (BCa can fail on low-variance samples)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.stats import bootstrap


@dataclass(frozen=True)
class Interval:
    """A point estimate with a bootstrap confidence interval."""

    kind: Literal["interval"]
    point: float
    low: float
    high: float


@dataclass(frozen=True)
class Abstention:
    """Refusal to emit a point estimate below the sample-size floor."""

    kind: Literal["abstention"]
    reason: str
    n_samples: int
    min_samples: int


type Estimate = Interval | Abstention


@dataclass(frozen=True)
class _BootstrapSettings:
    """Inputs to the internal interval calculation."""

    min_samples: int
    n_resamples: int
    confidence_level: float
    seed: int


def _bootstrap_mean(data: np.ndarray, settings: _BootstrapSettings) -> tuple[float, float]:
    result = bootstrap(
        (data,),
        np.mean,
        n_resamples=settings.n_resamples,
        confidence_level=settings.confidence_level,
        method="percentile",
        rng=settings.seed,
    )
    return float(result.confidence_interval.low), float(result.confidence_interval.high)


def _percentile_interval(data: np.ndarray, settings: _BootstrapSettings) -> Interval:
    low, high = _bootstrap_mean(data, settings)
    return Interval(
        kind="interval",
        point=float(np.mean(data)),
        low=low,
        high=high,
    )


def _estimate(samples: Sequence[float], settings: _BootstrapSettings) -> Estimate:
    count = len(samples)
    if count < settings.min_samples:
        return Abstention("abstention", "sample count below floor", count, settings.min_samples)
    return _percentile_interval(np.asarray(samples, dtype=float), settings)


def mean_interval(
    samples: Sequence[float],
    *,
    min_samples: int,
    n_resamples: int,
    confidence_level: float,
    seed: int,
) -> Estimate:
    """Bootstrap CI of the mean, or abstain below ``min_samples``."""
    settings = _BootstrapSettings(min_samples, n_resamples, confidence_level, seed)
    return _estimate(samples, settings)
