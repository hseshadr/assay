"""Stable, scoring-only Assay error codes."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

__all__ = [
    "AssayError",
    "CliInputInvalid",
    "ContractCode",
    "EmptyRelevantSet",
    "InsufficientSamples",
    "InvalidAgreementRequest",
    "InvalidMethod",
    "InvalidRankingRequest",
    "InvalidScoreRequest",
    "ReplayRefused",
    "ScoringCorePending",
    "ScoringExtraMissing",
    "UnknownMetric",
]


class ContractCode(StrEnum):
    """Stable, value-free validation codes for public scoring contracts."""

    DUPLICATE_IDENTIFIER = "assay.duplicate_identifier"
    EMPTY_COMPONENTS = "assay.empty_components"
    EMPTY_TERMS = "assay.empty_terms"
    INVALID_CLAMP_POLICY = "assay.invalid_clamp_policy"
    INVALID_COEFFICIENT = "assay.invalid_coefficient"
    INVALID_DIRECTION = "assay.invalid_direction"
    INVALID_IDENTIFIER = "assay.invalid_identifier"
    INVALID_INPUTS_HASH = "assay.invalid_inputs_hash"
    INVALID_INTERVAL = "assay.invalid_interval"
    INVALID_LABEL = "assay.invalid_label"
    INVALID_METHOD = "assay.invalid_method"
    INVALID_NUMBER = "assay.invalid_number"
    INVALID_OBJECT = "assay.invalid_object"
    INVALID_OPERATION = "assay.invalid_operation"
    INVALID_SCALE = "assay.invalid_scale"
    INVALID_TEXT = "assay.invalid_text"
    INVALID_WEIGHT = "assay.invalid_weight"
    MISSING_FIELD = "assay.missing_field"
    MISSING_WEIGHT = "assay.missing_weight"
    OUT_OF_RANGE = "assay.out_of_range"
    UNKNOWN_FIELD = "assay.unknown_field"


class AssayError(Exception):
    """Base class for Assay domain failures."""

    code: ClassVar[str] = "assay.error"

    def __init__(self, _detail: object | None = None) -> None:
        """Expose only the stable code; caller values never enter the message."""
        super().__init__(self.code)


class CliInputInvalid(AssayError):
    """A CLI input is unreadable, malformed, or unsafe."""

    code: ClassVar[str] = "assay.cli_input_invalid"


class InvalidScoreRequest(AssayError):
    """A score request cannot produce a meaningful result."""

    code: ClassVar[str] = "assay.invalid_request"


class InvalidMethod(AssayError):
    """A score request has no recognized combiner discriminator."""

    code: ClassVar[str] = "assay.invalid_method"


class UnknownMetric(AssayError):
    """A requested metric is not registered."""

    code: ClassVar[str] = "assay.unknown_metric"


class InvalidRankingRequest(AssayError):
    """A ranked-retrieval input cannot be scored as given."""

    code: ClassVar[str] = "assay.invalid_ranking_request"


class EmptyRelevantSet(AssayError):
    """A ranking has no judged-relevant document."""

    code: ClassVar[str] = "assay.empty_relevant_set"


class InvalidAgreementRequest(AssayError):
    """An inter-rater input cannot be scored as given."""

    code: ClassVar[str] = "assay.invalid_agreement_request"


class InsufficientSamples(AssayError):
    """A sample count is below the declared uncertainty floor."""

    code: ClassVar[str] = "assay.insufficient_samples"


class ScoringExtraMissing(AssayError):
    """An optional metric was requested without metric dependencies."""

    code: ClassVar[str] = "assay.scoring_extra_missing"


class ReplayRefused(AssayError):
    """A historical score cannot be reproduced from its inputs."""

    code: ClassVar[str] = "assay.replay_refused"


class ScoringCorePending(AssayError):
    """The transitional CLI has no scoring command until the core lands."""

    code: ClassVar[str] = "assay.scoring_core_pending"
