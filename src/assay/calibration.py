"""Calibration evidence: Expected Calibration Error (ECE), a reliability diagram,
and the Brier score.

Reliability points come from ``sklearn.calibration.calibration_curve`` (which drops
empty bins), bin populations from ``numpy.histogram`` over the same uniform edges,
and Brier from ``sklearn.metrics.brier_score_loss``. ECE is the population-weighted
gap between predicted confidence and observed frequency."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import SupportsInt, cast

from assay._optional import call_dependency, dependency_failed, load_callable
from assay.errors import InvalidScoreRequest
from assay.limits import MAX_CALIBRATION_BINS, MAX_ITEMS


@dataclass(frozen=True)
class ReliabilityBin:
    """One reliability-diagram point."""

    mean_predicted: float
    fraction_positive: float
    count: int


@dataclass(frozen=True)
class CalibrationReport:
    """ECE, Brier, and the reliability diagram for a set of predictions."""

    ece: float
    brier: float
    bins: tuple[ReliabilityBin, ...]


def _validate_shape(y_true: Sequence[int], y_score: Sequence[float], n_bins: int) -> None:
    if len(y_true) != len(y_score) or not y_true:
        raise InvalidScoreRequest
    if len(y_true) > MAX_ITEMS:
        raise InvalidScoreRequest
    _validate_bin_count(n_bins)


def _validate_bin_count(n_bins: int) -> None:
    if isinstance(n_bins, bool) or not 0 < n_bins <= MAX_CALIBRATION_BINS:
        raise InvalidScoreRequest


def _validate_labels(y_true: Sequence[int]) -> None:
    if set(y_true) - {0, 1}:
        raise InvalidScoreRequest


def _validate_scores(y_score: Sequence[float]) -> None:
    if not all(math.isfinite(score) and 0.0 <= score <= 1.0 for score in y_score):
        raise InvalidScoreRequest


def _validate(y_true: Sequence[int], y_score: Sequence[float], n_bins: int) -> None:
    _validate_shape(y_true, y_score, n_bins)
    _validate_labels(y_true)
    _validate_scores(y_score)


def _bin_populations(score_arr: object, n_bins: int) -> list[int]:
    # Bin with sklearn's own scheme (searchsorted on interior edges) rather than a
    # parallel np.histogram: at an exact bin edge the two disagree, which would
    # misalign these counts with calibration_curve's non-empty bins.
    edges = _call("numpy", "linspace", 0.0, 1.0, n_bins + 1)
    interior = call_dependency(_interior, edges)
    if dependency_failed(interior):
        raise InvalidScoreRequest
    bin_ids = _call("numpy", "searchsorted", interior, score_arr)
    counts = _call("numpy", "bincount", bin_ids, minlength=n_bins)
    converted = call_dependency(_positive_ints, counts)
    if dependency_failed(converted):
        raise InvalidScoreRequest
    return cast(list[int], converted)


def _interior(values: object) -> object:
    return values[1:-1]  # type: ignore[index]


def _positive_ints(values: object) -> list[int]:
    converted = [_as_int(value) for value in cast(Sequence[object], values)]
    return [value for value in converted if value > 0]


def _as_int(value: object) -> int:
    return int(cast(SupportsInt, value))


def _bins(
    prob_pred: Sequence[float], prob_true: Sequence[float], weights: list[int]
) -> list[ReliabilityBin]:
    bins = [
        ReliabilityBin(mean_predicted=float(p), fraction_positive=float(t), count=w)
        for p, t, w in zip(prob_pred, prob_true, weights, strict=True)
    ]
    if not all(
        math.isfinite(row.mean_predicted) and math.isfinite(row.fraction_positive) for row in bins
    ):
        raise InvalidScoreRequest
    return bins


def _ece(bins: list[ReliabilityBin], total: int) -> float:
    result = sum(b.count / total * abs(b.mean_predicted - b.fraction_positive) for b in bins)
    if not math.isfinite(result):
        raise InvalidScoreRequest
    return result


def _call(module: str, name: str, *args: object, **kwargs: object) -> object:
    result = call_dependency(load_callable(module, name), *args, **kwargs)
    if dependency_failed(result):
        raise InvalidScoreRequest
    return result


def _curve(
    true_arr: object, score_arr: object, n_bins: int
) -> tuple[Sequence[float], Sequence[float]]:
    raw = _call(
        "sklearn.calibration",
        "calibration_curve",
        true_arr,
        score_arr,
        n_bins=n_bins,
        strategy="uniform",
    )
    converted = call_dependency(_pair, raw)
    if dependency_failed(converted):
        raise InvalidScoreRequest
    return cast(tuple[Sequence[float], Sequence[float]], converted)


def _pair(value: object) -> tuple[Sequence[float], Sequence[float]]:
    first, second = cast(Sequence[Sequence[float]], value)
    return first, second


def _finite_float(value: object) -> float:
    converted = call_dependency(float, value)
    if dependency_failed(converted) or not math.isfinite(cast(float, converted)):
        raise InvalidScoreRequest
    return cast(float, converted)


def calibration_report(
    y_true: Sequence[int], y_score: Sequence[float], *, n_bins: int
) -> CalibrationReport:
    """Build the ECE / Brier / reliability report for binary predictions."""
    _validate(y_true, y_score, n_bins)
    true_arr = _call("numpy", "asarray", y_true, dtype=float)
    score_arr = _call("numpy", "asarray", y_score, dtype=float)
    prob_true, prob_pred = _curve(true_arr, score_arr, n_bins)
    bins = _bins(prob_pred, prob_true, _bin_populations(score_arr, n_bins))
    return CalibrationReport(
        ece=_ece(bins, total=len(y_score)),
        brier=_finite_float(_call("sklearn.metrics", "brier_score_loss", true_arr, score_arr)),
        bins=tuple(bins),
    )
