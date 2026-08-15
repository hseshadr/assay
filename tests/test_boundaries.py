"""Fail-closed boundaries for the retained scoring calculators."""

from __future__ import annotations

import pytest

from assay.composite import SubScore, composite
from assay.errors import InvalidScoreRequest
from assay.metrics import binary_scores


def test_should_reject_when_lengths_mismatch() -> None:
    # Given / When / Then
    with pytest.raises(InvalidScoreRequest):
        binary_scores([0, 1], [0.2])


def test_should_reject_when_inputs_are_empty() -> None:
    # Given / When / Then
    with pytest.raises(InvalidScoreRequest):
        binary_scores([], [])


def test_should_reject_composite_when_weights_are_not_positive() -> None:
    # Given
    subs = [
        SubScore("a", 0.5, 0.4, 0.6, 0.0, 1.0, 0.0),
        SubScore("b", 0.5, 0.4, 0.6, 0.0, 1.0, 0.0),
        SubScore("c", 0.5, 0.4, 0.6, 0.0, 1.0, 0.0),
    ]

    # When / Then
    with pytest.raises(InvalidScoreRequest):
        composite(subs)
