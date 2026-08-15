"""Stable, scoring-only Assay error codes."""

from __future__ import annotations

from typing import ClassVar

__all__ = [
    "AssayError",
    "CliInputInvalid",
    "EmptyRelevantSet",
    "InsufficientSamples",
    "InvalidAgreementRequest",
    "InvalidRankingRequest",
    "InvalidScoreRequest",
    "ReplayRefused",
    "ScoringCorePending",
    "ScoringExtraMissing",
    "UnknownMetric",
]


class AssayError(Exception):
    """Base class for Assay domain failures."""

    code: ClassVar[str] = "assay.error"


class CliInputInvalid(AssayError):
    """A CLI input is unreadable, malformed, or unsafe."""

    code: ClassVar[str] = "assay.cli_input_invalid"


class InvalidScoreRequest(AssayError):
    """A score request cannot produce a meaningful result."""

    code: ClassVar[str] = "assay.invalid_request"


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
