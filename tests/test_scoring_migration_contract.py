"""Pure scoring expectations preserved across the repository split.

These executable migration cases are conformance inputs for Tasks 2-5. They retain the
numeric and privacy behavior that used to be asserted only through signed receipts.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from assay.calibration import calibration_report
from assay.composite import SubScore, composite
from assay.metrics import binary_scores, correctness
from assay.uncertainty import Abstention, Interval, mean_interval

_TRUE = tuple([0, 1] * 20)
_SCORES = tuple([0.2, 0.8] * 20)


def _estimate(y_true: tuple[int, ...], scores: tuple[float, ...]) -> Interval | Abstention:
    samples = correctness(y_true, scores)
    return mean_interval(samples, min_samples=30, n_resamples=99, confidence_level=0.95, seed=0)


def _subscores() -> tuple[SubScore, ...]:
    return (
        SubScore("accuracy", 0.9, 0.85, 0.95, 0.0, 1.0, 1.0),
        SubScore("latency", 80.0, 70.0, 90.0, 0.0, 100.0, 1.0),
        SubScore("rating", 4.0, 3.5, 4.5, 1.0, 5.0, 2.0),
    )


def test_should_abstain_without_point_when_sample_is_thin() -> None:
    # Given / When
    estimate = _estimate((0, 1, 0, 1, 0), (0.2, 0.8, 0.3, 0.7, 0.4))

    # Then
    assert isinstance(estimate, Abstention)
    assert estimate.n_samples == 5
    assert estimate.min_samples == 30


def test_should_emit_interval_without_abstention_when_sample_meets_floor() -> None:
    # Given / When
    estimate = _estimate(_TRUE, _SCORES)

    # Then
    assert isinstance(estimate, Interval)
    assert estimate.point == 1.0
    assert estimate.low == 1.0
    assert estimate.high == 1.0


def test_should_preserve_reproducible_calibration_expectations() -> None:
    # Given / When
    first = calibration_report(_TRUE, _SCORES, n_bins=10)
    second = calibration_report(_TRUE, _SCORES, n_bins=10)

    # Then
    assert first.ece == pytest.approx(0.2)
    assert first.brier == pytest.approx(0.04)
    assert len(first.bins) == 2
    assert first == second


def test_should_preserve_weighted_composite_interval_expectations() -> None:
    # Given / When
    result = composite(_subscores())

    # Then
    assert result.value == pytest.approx(0.8)
    assert result.low == pytest.approx(0.7)
    assert result.high == pytest.approx(0.9)
    assert len(result.parts) == 3


def test_should_score_without_network_or_hidden_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    def refuse_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("runtime egress attempted")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(socket, "socket", refuse_socket)

    # When / Then
    assert binary_scores(_TRUE, _SCORES).accuracy == 1.0
    assert calibration_report(_TRUE, _SCORES, n_bins=10).ece == pytest.approx(0.2)
    assert composite(_subscores()).value == pytest.approx(0.8)
    assert tuple(tmp_path.iterdir()) == ()
