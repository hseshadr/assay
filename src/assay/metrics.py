"""Deterministic classification metrics — thin wrappers over scikit-learn.

Assay reimplements no metric math; it validates inputs, delegates to sklearn, and
returns an immutable, fully-typed result."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING

from assay.errors import InvalidScoreRequest, MetricsExtraMissing

if TYPE_CHECKING:
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        confusion_matrix,
        precision_recall_fscore_support,
        roc_auc_score,
    )
else:
    try:
        from sklearn.metrics import (
            accuracy_score,
            average_precision_score,
            confusion_matrix,
            precision_recall_fscore_support,
            roc_auc_score,
        )
    except ImportError:
        accuracy_score = None
        average_precision_score = None
        confusion_matrix = None
        precision_recall_fscore_support = None
        roc_auc_score = None

_MIN_CLASSES = 2
_METRICS_MODULES = ("numpy", "scipy", "sklearn", "ir_measures", "pydantic_settings")

_BINARY_LABELS = (0, 1)
"""The confusion matrix is pinned to these, in this order, so its orientation can never
depend on which labels happen to appear in the data."""


def require_metrics_extra() -> None:
    """Refuse optional calculators with one stable, value-free error."""
    try:
        for module in _METRICS_MODULES:
            import_module(module)
    except ImportError:
        raise MetricsExtraMissing from None


@dataclass(frozen=True)
class ConfusionCounts:
    """The four cells of a binary confusion matrix at one threshold.

    Named cells, not a bare 2x2 array. ``confusion_matrix(...).ravel()`` returns them in
    the order ``tn, fp, fn, tp``, and reading that tuple in the wrong order is the
    classic silent inversion: it swaps a miss for a false alarm while every total still
    adds up, so nothing downstream can notice."""

    true_negatives: int
    false_positives: int
    false_negatives: int
    true_positives: int


@dataclass(frozen=True)
class ClassificationScores:
    """Immutable bundle of binary-classification metrics."""

    accuracy: float
    precision: float
    recall: float
    f1: float
    pr_auc: float
    roc_auc: float
    counts: ConfusionCounts
    false_negative_rate: float


def _validate(y_true: Sequence[int], y_score: Sequence[float]) -> None:
    require_metrics_extra()
    if len(y_true) != len(y_score):
        raise InvalidScoreRequest
    if not y_true:
        raise InvalidScoreRequest
    if not all(math.isfinite(score) for score in y_score):
        raise InvalidScoreRequest
    _require_binary_labels(y_true)


def _require_auc_classes(y_true: Sequence[int]) -> None:
    if len(set(y_true)) < _MIN_CLASSES:
        raise InvalidScoreRequest


def _threshold(y_score: Sequence[float], threshold: float) -> list[int]:
    if not math.isfinite(threshold):
        raise InvalidScoreRequest
    return [1 if s >= threshold else 0 for s in y_score]


def _prf(y_true: Sequence[int], y_pred: Sequence[int]) -> tuple[float, float, float]:
    require_metrics_extra()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0.0
    )
    return float(precision), float(recall), float(f1)


def _require_binary_labels(y_true: Sequence[int]) -> None:
    """Every label must be 0 or 1.

    This refusal is what makes pinning ``labels=(0, 1)`` safe. sklearn silently DROPS
    every row whose label falls outside that pinning, so a stray 2 would vanish from the
    counts and the four cells would come back looking perfectly healthy, computed over
    fewer examples than the caller handed in."""
    outside = set(y_true) - set(_BINARY_LABELS)
    if outside:
        raise InvalidScoreRequest


def _counts(y_true: Sequence[int], y_pred: Sequence[int]) -> ConfusionCounts:
    require_metrics_extra()
    true_negatives, false_positives, false_negatives, true_positives = confusion_matrix(
        y_true, y_pred, labels=_BINARY_LABELS
    ).ravel()
    return ConfusionCounts(
        true_positives=int(true_positives),
        false_positives=int(false_positives),
        true_negatives=int(true_negatives),
        false_negatives=int(false_negatives),
    )


def confusion_counts(
    y_true: Sequence[int], y_score: Sequence[float], *, threshold: float = 0.5
) -> ConfusionCounts:
    """The four confusion cells at ``threshold``, from sklearn's confusion matrix.

    A rate hides which way a system fails. 200 misses and 2 false alarms produce the same
    accuracy as 2 misses and 200 false alarms, and only the counts tell them apart."""
    _validate(y_true, y_score)
    _require_binary_labels(y_true)
    return _counts(y_true, _threshold(y_score, threshold))


def _false_negative_rate(counts: ConfusionCounts) -> float:
    """Misses over real positives. The denominator cannot be zero: ``_validate`` already
    requires both classes in ``y_true``, so at least one real positive exists."""
    positives = counts.false_negatives + counts.true_positives
    if positives == 0:
        raise InvalidScoreRequest
    return counts.false_negatives / positives


def false_negative_rate(
    y_true: Sequence[int], y_score: Sequence[float], *, threshold: float = 0.5
) -> float:
    """The miss rate: of everything that really was positive, what fraction was called
    negative.

    Exactly ``1 - recall``, and named anyway. For a screening system the miss is the
    number it is judged on, and nobody reads a 3% miss rate off a recall of 0.97."""
    return _false_negative_rate(confusion_counts(y_true, y_score, threshold=threshold))


def _scores(
    y_true: Sequence[int], y_score: Sequence[float], y_pred: Sequence[int]
) -> ClassificationScores:
    precision, recall, f1 = _prf(y_true, y_pred)
    counts = _counts(y_true, y_pred)
    return ClassificationScores(
        accuracy=float(accuracy_score(y_true, y_pred)),
        precision=precision,
        recall=recall,
        f1=f1,
        pr_auc=float(average_precision_score(y_true, y_score)),
        roc_auc=float(roc_auc_score(y_true, y_score)),
        counts=counts,
        false_negative_rate=_false_negative_rate(counts),
    )


def binary_scores(
    y_true: Sequence[int], y_score: Sequence[float], *, threshold: float = 0.5
) -> ClassificationScores:
    """Compute accuracy, precision, recall, F1, PR-AUC, ROC-AUC, the four confusion
    counts and the false-negative rate."""
    _validate(y_true, y_score)
    _require_auc_classes(y_true)
    return _scores(y_true, y_score, _threshold(y_score, threshold))


def correctness(
    y_true: Sequence[int], y_score: Sequence[float], *, threshold: float = 0.5
) -> tuple[float, ...]:
    """Return a per-example 1.0/0.0 correctness vector (for bootstrapping)."""
    _validate(y_true, y_score)
    y_pred = _threshold(y_score, threshold)
    return tuple(float(int(p == t)) for p, t in zip(y_pred, y_true, strict=True))
