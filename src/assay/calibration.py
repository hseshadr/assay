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
from typing import TYPE_CHECKING

from assay.errors import InvalidScoreRequest
from assay.metrics import require_metrics_extra

if TYPE_CHECKING:
    import numpy as np
    from sklearn.calibration import calibration_curve
    from sklearn.metrics import brier_score_loss
else:
    try:
        import numpy as np
        from sklearn.calibration import calibration_curve
        from sklearn.metrics import brier_score_loss
    except ImportError:
        np = None
        calibration_curve = None
        brier_score_loss = None


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
    if len(y_true) != len(y_score) or not y_true or n_bins <= 0:
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
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_ids = np.searchsorted(edges[1:-1], np.asarray(score_arr, dtype=float))
    counts = np.bincount(bin_ids, minlength=n_bins)
    return [int(c) for c in counts if c > 0]


def _bins(
    prob_pred: Sequence[float], prob_true: Sequence[float], weights: list[int]
) -> list[ReliabilityBin]:
    return [
        ReliabilityBin(mean_predicted=float(p), fraction_positive=float(t), count=w)
        for p, t, w in zip(prob_pred, prob_true, weights, strict=True)
    ]


def _ece(bins: list[ReliabilityBin], total: int) -> float:
    return sum(b.count / total * abs(b.mean_predicted - b.fraction_positive) for b in bins)


def calibration_report(
    y_true: Sequence[int], y_score: Sequence[float], *, n_bins: int
) -> CalibrationReport:
    """Build the ECE / Brier / reliability report for binary predictions."""
    require_metrics_extra()
    _validate(y_true, y_score, n_bins)
    true_arr = np.asarray(y_true, dtype=float)
    score_arr = np.asarray(y_score, dtype=float)
    prob_true, prob_pred = calibration_curve(true_arr, score_arr, n_bins=n_bins, strategy="uniform")
    bins = _bins(prob_pred, prob_true, _bin_populations(score_arr, n_bins))
    return CalibrationReport(
        ece=_ece(bins, total=len(score_arr)),
        brier=float(brier_score_loss(true_arr, score_arr)),
        bins=tuple(bins),
    )
