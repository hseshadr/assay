"""Uncertainty with an honesty floor.

Above ``min_samples`` we return a percentile bootstrap confidence interval
(``scipy.stats.bootstrap``, fixed seed → reproducible). Below the floor we return
an ``Abstention`` — never a point estimate the data cannot support. ``percentile``
is chosen over ``BCa`` because it is robust and fully deterministic with a fixed
seed (BCa can fail on low-variance samples)."""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from assay._optional import call_dependency, dependency_failed, load_callable
from assay.errors import InvalidScoreRequest
from assay.limits import (
    MAX_BOOTSTRAP_BATCH_CELLS,
    MAX_BOOTSTRAP_RESAMPLES,
    MAX_BOOTSTRAP_WORK_CELLS,
    MAX_ITEMS,
    MAX_SEED,
)


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


class _ConfidenceBounds(Protocol):
    low: object
    high: object


class _BootstrapResult(Protocol):
    confidence_interval: _ConfidenceBounds


def _bootstrap_mean(data: Sequence[float], settings: _BootstrapSettings) -> tuple[float, float]:
    bounds = call_dependency(_confidence_bounds, _bootstrap_result(data, settings))
    if dependency_failed(bounds):
        raise InvalidScoreRequest
    low, high = cast(tuple[object, object], bounds)
    return _finite_float(low), _finite_float(high)


def _bootstrap_result(data: Sequence[float], settings: _BootstrapSettings) -> object:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return _call(
            "scipy.stats",
            "bootstrap",
            (data,),
            load_callable("numpy", "mean"),
            n_resamples=settings.n_resamples,
            confidence_level=settings.confidence_level,
            method="percentile",
            rng=settings.seed,
            batch=_batch_size(len(data), settings.n_resamples),
        )


def _batch_size(sample_count: int, resamples: int) -> int:
    cells_per_batch = max(1, MAX_BOOTSTRAP_BATCH_CELLS // max(1, sample_count))
    return min(resamples, cells_per_batch)


def _confidence_bounds(result: object) -> tuple[object, object]:
    interval = cast(_BootstrapResult, result).confidence_interval
    return interval.low, interval.high


def _percentile_interval(data: Sequence[float], settings: _BootstrapSettings) -> Interval:
    if len(set(data)) == 1:
        point = data[0]
        return Interval(kind="interval", point=point, low=point, high=point)
    low, high = _bootstrap_mean(data, settings)
    return Interval(
        kind="interval",
        point=_finite_float(_call("numpy", "mean", data)),
        low=low,
        high=high,
    )


def _estimate(samples: Sequence[float], settings: _BootstrapSettings) -> Estimate:
    count = len(samples)
    if count < settings.min_samples:
        return Abstention("abstention", "sample count below floor", count, settings.min_samples)
    return _percentile_interval(samples, settings)


def _validate_settings(settings: _BootstrapSettings) -> None:
    _validate_positive_count(settings.min_samples, MAX_ITEMS)
    _validate_positive_count(settings.n_resamples, MAX_BOOTSTRAP_RESAMPLES)
    if isinstance(settings.seed, bool) or not 0 <= settings.seed <= MAX_SEED:
        raise InvalidScoreRequest
    _validate_confidence(settings.confidence_level)


def _validate_positive_count(value: int, maximum: int) -> None:
    if isinstance(value, bool) or not 0 < value <= maximum:
        raise InvalidScoreRequest


def _validate_confidence(value: float) -> None:
    if not _is_finite_number(value) or not 0.0 < value < 1.0:
        raise InvalidScoreRequest


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _validate_samples(samples: Sequence[float]) -> None:
    if len(samples) > MAX_ITEMS or not all(_is_finite_number(sample) for sample in samples):
        raise InvalidScoreRequest


def _validate(samples: Sequence[float], settings: _BootstrapSettings) -> None:
    _validate_settings(settings)
    _validate_samples(samples)
    if len(samples) * settings.n_resamples > MAX_BOOTSTRAP_WORK_CELLS:
        raise InvalidScoreRequest


def _call(module: str, name: str, *args: object, **kwargs: object) -> object:
    result = call_dependency(load_callable(module, name), *args, **kwargs)
    if dependency_failed(result):
        raise InvalidScoreRequest
    return result


def _finite_float(value: object) -> float:
    converted = call_dependency(float, value)
    if dependency_failed(converted) or not math.isfinite(cast(float, converted)):
        raise InvalidScoreRequest
    return cast(float, converted)


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
    _validate(samples, settings)
    load_callable("numpy", "mean")
    load_callable("scipy.stats", "bootstrap")
    return _estimate(samples, settings)
