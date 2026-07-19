from __future__ import annotations

import pytest

from assay.composite import SubScore, composite
from assay.errors import InvalidScoreRequest


def _three_subscores() -> list[SubScore]:
    return [
        SubScore("accuracy", 0.9, 0.85, 0.95, 0.0, 1.0, 1.0),
        SubScore("latency", 80.0, 70.0, 90.0, 0.0, 100.0, 1.0),
        SubScore("rating", 4.0, 3.5, 4.5, 1.0, 5.0, 2.0),
    ]


def test_should_combine_multi_scale_subscores_with_propagated_interval() -> None:
    # Given three sub-scores on [0,1], [0,100] and [1,5] scales with weights 1,1,2
    subscores = _three_subscores()
    # When composited
    result = composite(subscores)
    # Then the normalized weighted value and propagated bounds are exact
    assert result.value == pytest.approx(0.8)
    assert result.low == pytest.approx(0.7)
    assert result.high == pytest.approx(0.9)
    assert result.low < result.value < result.high
    assert len(result.parts) == 3


def test_should_reject_fewer_than_three_subscores() -> None:
    # Given only two sub-scores
    subscores = _three_subscores()[:2]
    # When composited
    # Then it is rejected (v0 requires >= 3 different scales)
    with pytest.raises(InvalidScoreRequest):
        composite(subscores)


def test_should_reject_non_increasing_scale() -> None:
    # Given a sub-score whose scale_max <= scale_min
    bad = [SubScore("x", 1.0, 1.0, 1.0, 5.0, 5.0, 1.0), *_three_subscores()[:2]]
    # When composited
    # Then it is rejected
    with pytest.raises(InvalidScoreRequest):
        composite(bad)
