"""Metric controls stay finite, bounded, and value-free on failure."""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable

import pytest
import sklearn.calibration

from assay import _optional
from assay.calibration import calibration_report
from assay.errors import InvalidRankingRequest, InvalidScoreRequest
from assay.metrics import confusion_counts
from assay.ranking import ndcg_at_k
from assay.uncertainty import mean_interval


@pytest.mark.parametrize(
    "call",
    [
        lambda: confusion_counts([0, 1], [0.1, 0.9], threshold=True),
        lambda: calibration_report([0, 1], [0.1, 0.9], n_bins=True),
        lambda: calibration_report([0, 1], [0.1, 0.9], n_bins=10**100),
        lambda: mean_interval([0.0], min_samples=True, n_resamples=9, confidence_level=0.9, seed=0),
        lambda: mean_interval([0.0], min_samples=1, n_resamples=True, confidence_level=0.9, seed=0),
        lambda: mean_interval(
            [0.0], min_samples=1, n_resamples=10**100, confidence_level=0.9, seed=0
        ),
        lambda: mean_interval([0.0], min_samples=1, n_resamples=9, confidence_level=True, seed=0),
        lambda: mean_interval([0.0], min_samples=1, n_resamples=9, confidence_level=0.9, seed=True),
    ],
)
def test_should_refuse_boolean_or_unbounded_numeric_controls(call: Callable[[], object]) -> None:
    with pytest.raises(InvalidScoreRequest) as caught:
        call()
    assert str(caught.value) == "assay.invalid_request"


@pytest.mark.parametrize(
    "call",
    [
        lambda: ndcg_at_k({"doc": 1.0}, ["doc"], True),
        lambda: ndcg_at_k({"doc": 1.0}, ["doc"], 10**100),
        lambda: ndcg_at_k({"doc": True}, ["doc"], 1),
        lambda: ndcg_at_k({"doc": 10**100}, ["doc"], 1),
    ],
)
def test_should_refuse_boolean_or_unbounded_ranking_controls(call: Callable[[], object]) -> None:
    with pytest.raises(InvalidRankingRequest) as caught:
        call()
    assert str(caught.value) == "assay.invalid_ranking_request"


def test_should_refuse_a_nonfinite_bootstrap_result_from_huge_finite_samples() -> None:
    samples = [1e308, 1e308, -1e308, -1e308]
    with pytest.raises(InvalidScoreRequest) as caught:
        mean_interval(
            samples,
            min_samples=1,
            n_resamples=99,
            confidence_level=0.95,
            seed=0,
        )
    assert str(caught.value) == "assay.invalid_request"
    assert all(math.isfinite(sample) for sample in samples)


def test_should_suppress_dependency_warnings_for_a_rejected_bootstrap() -> None:
    private_value = 1e308
    samples = [private_value, private_value, -private_value, -private_value]
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always", RuntimeWarning)
        with pytest.raises(InvalidScoreRequest) as caught:
            mean_interval(
                samples,
                min_samples=1,
                n_resamples=99,
                confidence_level=0.95,
                seed=0,
            )
    assert emitted == []
    assert str(caught.value) == "assay.invalid_request"
    assert "1e+308" not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_should_reject_calibration_bounds_before_calling_sklearn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def mark_called(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        raise RuntimeError

    monkeypatch.setattr(sklearn.calibration, "calibration_curve", mark_called)
    _optional.load_callable.cache_clear()
    with pytest.raises(InvalidScoreRequest):
        calibration_report([0, 1], [0.1, 0.9], n_bins=10**100)
    assert not called
