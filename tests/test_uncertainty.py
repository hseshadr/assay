from __future__ import annotations

import math

import pytest

from assay.errors import InvalidScoreRequest
from assay.uncertainty import Abstention, Interval, mean_interval

_KW = {"n_resamples": 999, "confidence_level": 0.95, "seed": 12345}


def test_should_abstain_when_below_sample_floor() -> None:
    # Given fewer samples than the floor
    samples = [1.0, 0.0, 1.0, 1.0, 0.0]
    # When an interval is requested with a floor of 30
    estimate = mean_interval(samples, min_samples=30, **_KW)
    # Then it abstains instead of inventing a point number
    assert isinstance(estimate, Abstention)
    assert estimate.n_samples == 5
    assert estimate.min_samples == 30


def test_should_collapse_interval_when_variance_is_zero() -> None:
    # Given 50 identical samples (no spread) above the floor
    samples = [1.0] * 50
    # When an interval is requested
    estimate = mean_interval(samples, min_samples=30, **_KW)
    # Then it is a degenerate interval pinned at the point
    assert isinstance(estimate, Interval)
    assert estimate.point == 1.0
    assert estimate.low == 1.0
    assert estimate.high == 1.0


def test_should_collapse_a_single_sample_when_floor_allows_it() -> None:
    # Given one sample at an explicitly one-sample floor
    # When an interval is requested
    estimate = mean_interval([0.4], min_samples=1, **_KW)
    # Then the deterministic distribution collapses without asking scipy to resample it
    assert estimate == Interval(kind="interval", point=0.4, low=0.4, high=0.4)


def test_should_bracket_the_point_and_be_reproducible() -> None:
    # Given a balanced 0/1 sample above the floor
    samples = [0.0] * 50 + [1.0] * 50
    # When the interval is computed twice with the same seed
    first = mean_interval(samples, min_samples=30, **_KW)
    second = mean_interval(samples, min_samples=30, **_KW)
    # Then it brackets 0.5 and is byte-identical across runs
    assert isinstance(first, Interval)
    assert first.point == 0.5
    assert first.low < 0.5 < first.high
    assert (first.low, first.high) == (second.low, second.high)


@pytest.mark.parametrize(
    ("samples", "min_samples", "n_resamples", "confidence_level"),
    [
        ([0.0], 0, 99, 0.95),
        ([0.0], -1, 99, 0.95),
        ([0.0], 1, 0, 0.95),
        ([0.0], 1, -1, 0.95),
        ([0.0], 1, 99, 0.0),
        ([0.0], 1, 99, 1.0),
        ([0.0], 1, 99, math.nan),
        ([math.inf], 1, 99, 0.95),
    ],
)
def test_should_refuse_invalid_interval_bounds_with_stable_code(
    samples: list[float], min_samples: int, n_resamples: int, confidence_level: float
) -> None:
    # Given invalid uncertainty data or settings
    # When an estimate is requested
    with pytest.raises(InvalidScoreRequest) as caught:
        mean_interval(
            samples,
            min_samples=min_samples,
            n_resamples=n_resamples,
            confidence_level=confidence_level,
            seed=0,
        )
    # Then the error is stable and contains no caller value
    assert str(caught.value) == "assay.invalid_request"
