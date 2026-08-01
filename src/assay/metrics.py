"""Deterministic classification metrics — thin wrappers over scikit-learn.

Assay reimplements no metric math; it validates inputs, delegates to sklearn, and
returns an immutable, fully-typed result."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

from assay.errors import InvalidScoreRequest

_MIN_CLASSES = 2


@dataclass(frozen=True)
class ClassificationScores:
    """Immutable bundle of binary-classification metrics."""

    accuracy: float
    precision: float
    recall: float
    f1: float
    pr_auc: float
    roc_auc: float


def _validate(y_true: Sequence[int], y_score: Sequence[float]) -> None:
    if len(y_true) != len(y_score):
        raise InvalidScoreRequest("y_true and y_score length mismatch")
    if len(y_true) == 0:
        raise InvalidScoreRequest("inputs are empty")
    if len(set(y_true)) < _MIN_CLASSES:
        raise InvalidScoreRequest("need both classes present for AUC metrics")


def _threshold(y_score: Sequence[float], threshold: float) -> list[int]:
    return [1 if s >= threshold else 0 for s in y_score]


def _prf(y_true: Sequence[int], y_pred: Sequence[int]) -> tuple[float, float, float]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0.0
    )
    return float(precision), float(recall), float(f1)


def binary_scores(
    y_true: Sequence[int], y_score: Sequence[float], *, threshold: float = 0.5
) -> ClassificationScores:
    """Compute accuracy, precision, recall, F1, PR-AUC and ROC-AUC."""
    _validate(y_true, y_score)
    y_pred = _threshold(y_score, threshold)
    precision, recall, f1 = _prf(y_true, y_pred)
    return ClassificationScores(
        accuracy=float(accuracy_score(y_true, y_pred)),
        precision=precision,
        recall=recall,
        f1=f1,
        pr_auc=float(average_precision_score(y_true, y_score)),
        roc_auc=float(roc_auc_score(y_true, y_score)),
    )


def correctness(
    y_true: Sequence[int], y_score: Sequence[float], *, threshold: float = 0.5
) -> tuple[float, ...]:
    """Return a per-example 1.0/0.0 correctness vector (for bootstrapping)."""
    _validate(y_true, y_score)
    y_pred = _threshold(y_score, threshold)
    return tuple(float(int(p == t)) for p, t in zip(y_pred, y_true, strict=True))


def _protection_probe() -> int:
    """Deliberately broken: unused import + bad types, to make `gate` go red.

    This exists only to prove branch protection refuses a red PR. Delete on sight.
    """
    import os  # noqa placeholder removed on purpose so ruff flags it
    unused_variable = "this trips ruff F841"
    return "not an int"
