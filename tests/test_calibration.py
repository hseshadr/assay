from __future__ import annotations

import math

import pytest
from sklearn.metrics import brier_score_loss

from assay.calibration import calibration_report
from assay.errors import InvalidScoreRequest


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


def test_should_not_average_reliability_gaps_as_equal_sized_bins() -> None:
    # Given one low-bin example and three high-bin examples with different gaps
    y_true = [0, 0, 1, 1]
    y_score = [0.1, 0.8, 0.8, 0.8]
    # When ECE is computed over two non-empty bins
    report = calibration_report(y_true, y_score, n_bins=5)
    # Then each gap gets its population share: 1/4*0.1 + 3/4*|0.8-2/3| = 0.125
    assert report.ece == pytest.approx(0.125)
    assert tuple(row.count for row in report.bins) == (1, 3)


def test_should_delegate_brier_to_sklearn() -> None:
    # Given a miscalibrated set
    y_true = [0, 1, 0, 1]
    y_score = [0.2, 0.8, 0.6, 0.7]
    # When a report is built
    report = calibration_report(y_true, y_score, n_bins=5)
    # Then Brier equals sklearn's own brier_score_loss (reuse, not reimplement)
    assert report.brier == pytest.approx(float(brier_score_loss(y_true, y_score)))


def test_should_assign_an_exact_uniform_edge_like_sklearn() -> None:
    # Given probabilities exactly on and immediately above the first uniform edge
    y_true = [0, 1, 1]
    y_score = [0.0, 0.2, 0.20000000000000004]
    # When the five-bin reliability diagram is built
    report = calibration_report(y_true, y_score, n_bins=5)
    # Then sklearn's left-edge membership is preserved and empty bins are omitted
    assert tuple(row.count for row in report.bins) == (2, 1)
    assert tuple(row.mean_predicted for row in report.bins) == pytest.approx((0.1, y_score[2]))


@pytest.mark.parametrize(
    ("y_true", "y_score", "n_bins"),
    [
        ([0], [0.1, 0.2], 2),
        ([], [], 2),
        ([0, 2], [0.1, 0.9], 2),
        ([0, 1], [-0.1, 0.9], 2),
        ([0, 1], [0.1, 1.1], 2),
        ([0, 1], [0.1, math.nan], 2),
        ([0, 1], [0.1, math.inf], 2),
        ([0, 1], [0.1, 0.9], 0),
    ],
)
def test_should_refuse_invalid_calibration_inputs_with_stable_code(
    y_true: list[int], y_score: list[float], n_bins: int
) -> None:
    # Given an input for which calibration is undefined
    # When the report is requested
    with pytest.raises(InvalidScoreRequest) as caught:
        calibration_report(y_true, y_score, n_bins=n_bins)
    # Then the boundary exposes only a stable value-free code
    assert str(caught.value) == "assay.invalid_request"
