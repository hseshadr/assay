from __future__ import annotations

import pytest

from assay.errors import InvalidScoreRequest
from assay.metrics import binary_scores, correctness


def test_should_score_perfect_separation_as_one() -> None:
    # Given a perfectly separable binary problem
    y_true = [0, 0, 1, 1]
    y_score = [0.1, 0.2, 0.8, 0.9]
    # When scored at threshold 0.5
    scores = binary_scores(y_true, y_score, threshold=0.5)
    # Then every rank/threshold metric is 1.0
    assert scores.accuracy == 1.0
    assert scores.precision == 1.0
    assert scores.recall == 1.0
    assert scores.f1 == 1.0
    assert scores.pr_auc == pytest.approx(1.0)
    assert scores.roc_auc == pytest.approx(1.0)


def test_should_match_known_roc_auc_of_075() -> None:
    # Given the canonical sklearn ranking example
    y_true = [0, 0, 1, 1]
    y_score = [0.1, 0.4, 0.35, 0.8]
    # When scored
    scores = binary_scores(y_true, y_score)
    # Then ROC-AUC is exactly 0.75
    assert scores.roc_auc == pytest.approx(0.75)


def test_should_return_per_example_correctness_vector() -> None:
    # Given one right and one wrong prediction at threshold 0.5
    y_true = [1, 0]
    y_score = [0.9, 0.9]
    # When computing correctness
    hits = correctness(y_true, y_score, threshold=0.5)
    # Then it is 1.0 for the hit and 0.0 for the miss
    assert hits == (1.0, 0.0)


def test_should_raise_when_only_one_class_present() -> None:
    # Given labels with a single class (AUC undefined)
    with pytest.raises(InvalidScoreRequest):
        binary_scores([1, 1, 1], [0.2, 0.8, 0.5])
