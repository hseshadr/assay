"""Stable error-code contracts retained by the scoring-only package."""

from __future__ import annotations

import pytest

from assay.errors import (
    AssayError,
    CliExtraMissing,
    CliInputInvalid,
    CliOutputInvalid,
    CommandMovedToAvow,
    CommandReplaced,
    EmptyRelevantSet,
    InsufficientSamples,
    InvalidAgreementRequest,
    InvalidRankingRequest,
    InvalidScoreRequest,
    InvalidSettings,
    MetricsExtraMissing,
    ReplayRefused,
    UnknownMetric,
)

_ASSAY_CODES = [
    (CliExtraMissing, "assay.cli_extra_missing"),
    (CliInputInvalid, "assay.cli_input_invalid"),
    (CliOutputInvalid, "assay.cli_output_invalid"),
    (CommandMovedToAvow, "assay.command_moved_to_avow"),
    (CommandReplaced, "assay.command_replaced"),
    (InvalidScoreRequest, "assay.invalid_request"),
    (InvalidRankingRequest, "assay.invalid_ranking_request"),
    (InvalidAgreementRequest, "assay.invalid_agreement_request"),
    (EmptyRelevantSet, "assay.empty_relevant_set"),
    (UnknownMetric, "assay.unknown_metric"),
    (InsufficientSamples, "assay.insufficient_samples"),
    (MetricsExtraMissing, "assay.metrics_extra_missing"),
    (InvalidSettings, "assay.invalid_settings"),
    (ReplayRefused, "assay.replay_refused"),
]


@pytest.mark.parametrize(("error_cls", "code"), _ASSAY_CODES)
def test_should_carry_stable_assay_code_when_raised(error_cls: type[AssayError], code: str) -> None:
    # Given / When
    with pytest.raises(AssayError) as caught:
        raise error_cls("safe detail")

    # Then
    assert caught.value.code == code
