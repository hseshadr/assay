"""One explicit dispatcher for Assay's closed composition methods."""

from __future__ import annotations

from typing import overload

from assay.additive import additive
from assay.contracts import AdditiveRequest, MinimumRequest, ScoreResult, WeightedMeanRequest
from assay.minimum import minimum
from assay.weighted_mean import weighted_mean


@overload
def compose(request: WeightedMeanRequest) -> ScoreResult: ...


@overload
def compose(request: AdditiveRequest) -> ScoreResult: ...


@overload
def compose(request: MinimumRequest) -> ScoreResult: ...


def compose(request: WeightedMeanRequest | AdditiveRequest | MinimumRequest) -> ScoreResult:
    """Dispatch one validated request without accepting executable formulas."""
    if isinstance(request, WeightedMeanRequest):
        return weighted_mean(request)
    if isinstance(request, AdditiveRequest):
        return additive(request)
    return minimum(request)
