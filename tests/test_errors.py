"""Stable error-code contracts retained by the scoring-only package."""

from __future__ import annotations

import pytest

from assay.errors import (
    AssayError,
    CliInputInvalid,
    EmptyRelevantSet,
    InsufficientSamples,
    InvalidAgreementRequest,
    InvalidRankingRequest,
    InvalidScoreRequest,
    MetricsExtraMissing,
    ReplayRefused,
    ScoringCorePending,
    UnknownMetric,
)

_ASSAY_CODES = [
    (CliInputInvalid, "assay.cli_input_invalid"),
    (InvalidScoreRequest, "assay.invalid_request"),
    (InvalidRankingRequest, "assay.invalid_ranking_request"),
    (InvalidAgreementRequest, "assay.invalid_agreement_request"),
    (EmptyRelevantSet, "assay.empty_relevant_set"),
    (UnknownMetric, "assay.unknown_metric"),
    (InsufficientSamples, "assay.insufficient_samples"),
    (MetricsExtraMissing, "assay.metrics_extra_missing"),
    (ReplayRefused, "assay.replay_refused"),
    (ScoringCorePending, "assay.scoring_core_pending"),
]


@pytest.mark.parametrize(("error_cls", "code"), _ASSAY_CODES)
def test_should_carry_stable_assay_code_when_raised(error_cls: type[AssayError], code: str) -> None:
    # Given / When
    with pytest.raises(AssayError) as caught:
        raise error_cls("safe detail")

    # Then
    assert caught.value.code == code
