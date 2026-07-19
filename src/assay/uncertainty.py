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


def _percentile_interval(
    data: np.ndarray, *, n_resamples: int, confidence_level: float, seed: int
) -> Interval:
    result = bootstrap(
        (data,),
        np.mean,
        n_resamples=n_resamples,
        confidence_level=confidence_level,
        method="percentile",
        rng=seed,
    )
    ci = result.confidence_interval
    return Interval(
        kind="interval",
        point=float(np.mean(data)),
        low=float(ci.low),
        high=float(ci.high),
    )


def mean_interval(
    samples: Sequence[float],
    *,
    min_samples: int,
    n_resamples: int,
    confidence_level: float,
    seed: int,
) -> Estimate:
    """Bootstrap CI of the mean, or abstain below ``min_samples``."""
    n = len(samples)
    if n < min_samples:
        return Abstention(
            kind="abstention",
            reason="sample count below floor",
            n_samples=n,
            min_samples=min_samples,
        )
    data = np.asarray(samples, dtype=float)
    return _percentile_interval(
        data, n_resamples=n_resamples, confidence_level=confidence_level, seed=seed
    )
