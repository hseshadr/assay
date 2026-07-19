from __future__ import annotations

import pytest
from sklearn.metrics import brier_score_loss

from assay.calibration import calibration_report


def test_should_report_zero_ece_when_perfectly_confident() -> None:
    # Given perfectly-confident, perfectly-correct probabilities
    y_true = [0, 0, 1, 1]
    y_score = [0.0, 0.0, 1.0, 1.0]
    # When a 5-bin calibration report is built
    report = calibration_report(y_true, y_score, n_bins=5)
    # Then ECE and Brier are zero and there are two reliability bins
    assert report.ece == pytest.approx(0.0)
    assert report.brier == pytest.approx(0.0)
    assert len(report.bins) == 2


def test_should_weight_ece_by_bin_population() -> None:
    # Given four samples all predicted 0.3 but half are positive
    y_true = [0, 0, 1, 1]
    y_score = [0.3, 0.3, 0.3, 0.3]
    # When a 5-bin report is built
    report = calibration_report(y_true, y_score, n_bins=5)
    # Then ECE is |mean_pred - frac_pos| = |0.3 - 0.5| = 0.2
    assert report.ece == pytest.approx(0.2)
    assert report.bins[0].count == 4


def test_should_delegate_brier_to_sklearn() -> None:
    # Given a miscalibrated set
    y_true = [0, 1, 0, 1]
    y_score = [0.2, 0.8, 0.6, 0.7]
    # When a report is built
    report = calibration_report(y_true, y_score, n_bins=5)
    # Then Brier equals sklearn's own brier_score_loss (reuse, not reimplement)
    assert report.brier == pytest.approx(float(brier_score_loss(y_true, y_score)))
