"""Uncertainty with an honesty floor.

Above ``min_samples`` we return a percentile bootstrap confidence interval
(``scipy.stats.bootstrap``, fixed seed → reproducible). Below the floor we return
an ``Abstention`` — never a point estimate the data cannot support. ``percentile``
is chosen over ``BCa`` because it is robust and fully deterministic with a fixed
seed (BCa can fail on low-variance samples)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import TYPE_CHECKING, Literal

from assay.errors import InvalidScoreRequest
from assay.metrics import require_metrics_extra

if TYPE_CHECKING:
    import numpy as np
    from scipy.stats import bootstrap
else:
    try:
        import numpy as np
        from scipy.stats import bootstrap
    except ImportError:
        np = None
        bootstrap = None


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


def _bootstrap_mean(data: Sequence[float], settings: _BootstrapSettings) -> tuple[float, float]:
    result = bootstrap(
        (data,),
        np.mean,
        n_resamples=settings.n_resamples,
        confidence_level=settings.confidence_level,
        method="percentile",
        rng=settings.seed,
    )
    return float(result.confidence_interval.low), float(result.confidence_interval.high)


def _percentile_interval(data: Sequence[float], settings: _BootstrapSettings) -> Interval:
    if len(set(data)) == 1:
        point = data[0]
        return Interval(kind="interval", point=point, low=point, high=point)
    low, high = _bootstrap_mean(data, settings)
    return Interval(
        kind="interval",
        point=fmean(data),
        low=low,
        high=high,
    )


def _estimate(samples: Sequence[float], settings: _BootstrapSettings) -> Estimate:
    count = len(samples)
    if count < settings.min_samples:
        return Abstention("abstention", "sample count below floor", count, settings.min_samples)
    return _percentile_interval(samples, settings)


def _validate_settings(settings: _BootstrapSettings) -> None:
    if settings.min_samples <= 0 or settings.n_resamples <= 0:
        raise InvalidScoreRequest
    confidence = settings.confidence_level
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise InvalidScoreRequest


def _validate_samples(samples: Sequence[float]) -> None:
    if not all(math.isfinite(sample) for sample in samples):
        raise InvalidScoreRequest


def _validate(samples: Sequence[float], settings: _BootstrapSettings) -> None:
    _validate_settings(settings)
    _validate_samples(samples)


def mean_interval(
    samples: Sequence[float],
    *,
    min_samples: int,
    n_resamples: int,
    confidence_level: float,
    seed: int,
) -> Estimate:
    """Bootstrap CI of the mean, or abstain below ``min_samples``."""
    require_metrics_extra()
    settings = _BootstrapSettings(min_samples, n_resamples, confidence_level, seed)
    _validate(samples, settings)
    return _estimate(samples, settings)
