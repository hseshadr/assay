"""Stable, scoring-only Assay error codes."""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AssayError",
    "CliInputInvalid",
    "ContractCode",
    "ContractValidationError",
    "EmptyRelevantSet",
    "InsufficientSamples",
    "InvalidAgreementRequest",
    "InvalidMethod",
    "InvalidRankingRequest",
    "InvalidScoreRequest",
    "InvalidSettings",
    "MetricsExtraMissing",
    "ReplayRefused",
    "ScoringCorePending",
    "UnknownMetric",
]


class ContractCode(StrEnum):
    """Stable, value-free validation codes for public scoring contracts."""

    DUPLICATE_IDENTIFIER = "assay.duplicate_identifier"
    DUPLICATE_FIELD = "assay.duplicate_field"
    EMPTY_COMPONENTS = "assay.empty_components"
    EMPTY_TERMS = "assay.empty_terms"
    INVALID_CLAMP_POLICY = "assay.invalid_clamp_policy"
    INVALID_COEFFICIENT = "assay.invalid_coefficient"
    INVALID_CONTRACT = "assay.invalid_contract"
    INVALID_DIRECTION = "assay.invalid_direction"
    INVALID_IDENTIFIER = "assay.invalid_identifier"
    INVALID_INPUTS_HASH = "assay.invalid_inputs_hash"
    INVALID_ALIAS_CONFIG = "assay.invalid_alias_config"
    INVALID_INTERVAL = "assay.invalid_interval"
    INVALID_LABEL = "assay.invalid_label"
    INVALID_METHOD = "assay.invalid_method"
    INVALID_NUMBER = "assay.invalid_number"
    INVALID_OBJECT = "assay.invalid_object"
    INVALID_OPERATION = "assay.invalid_operation"
    INVALID_RESULT = "assay.invalid_result"
    INVALID_SCALE = "assay.invalid_scale"
    INVALID_TEXT = "assay.invalid_text"
    INVALID_WEIGHT = "assay.invalid_weight"
    MISSING_FIELD = "assay.missing_field"
    MISSING_WEIGHT = "assay.missing_weight"
    OUT_OF_RANGE = "assay.out_of_range"
    UNKNOWN_FIELD = "assay.unknown_field"


class AssayError(Exception):
    """Base class for Assay domain failures."""

    code: str = "assay.error"

    def __init__(self, _detail: object | None = None) -> None:
        """Expose only the stable code; caller values never enter the message."""
        super().__init__(self.code)


class ContractValidationError(AssayError):
    """A value-free public failure at an Assay JSON model boundary."""

    code: str = ContractCode.INVALID_CONTRACT.value

    def __init__(self, code: ContractCode = ContractCode.INVALID_CONTRACT) -> None:
        self.code = code.value
        super().__init__()


class CliInputInvalid(AssayError):
    """A CLI input is unreadable, malformed, or unsafe."""

    code: str = "assay.cli_input_invalid"


class InvalidScoreRequest(AssayError):
    """A score request cannot produce a meaningful result."""

    code: str = "assay.invalid_request"


class InvalidMethod(AssayError):
    """A score request has no recognized combiner discriminator."""

    code: str = "assay.invalid_method"


class UnknownMetric(AssayError):
    """A requested metric is not registered."""

    code: str = "assay.unknown_metric"


class InvalidRankingRequest(AssayError):
    """A ranked-retrieval input cannot be scored as given."""

    code: str = "assay.invalid_ranking_request"


class EmptyRelevantSet(AssayError):
    """A ranking has no judged-relevant document."""

    code: str = "assay.empty_relevant_set"


class InvalidAgreementRequest(AssayError):
    """An inter-rater input cannot be scored as given."""

    code: str = "assay.invalid_agreement_request"


class InsufficientSamples(AssayError):
    """A sample count is below the declared uncertainty floor."""

    code: str = "assay.insufficient_samples"


class MetricsExtraMissing(AssayError):
    """An optional metric was requested without metric dependencies."""

    code: str = "assay.metrics_extra_missing"


class InvalidSettings(AssayError):
    """Runtime settings are invalid or outside documented resource bounds."""

    code: str = "assay.invalid_settings"


class ReplayRefused(AssayError):
    """A historical score cannot be reproduced from its inputs."""

    code: str = "assay.replay_refused"


class ScoringCorePending(AssayError):
    """The transitional CLI has no scoring command until the core lands."""

    code: str = "assay.scoring_core_pending"
