"""Coded domain-error catalog for the *scoring* face. Every failure raises a typed
``AssayError`` with a stable string ``code`` so callers (and the CLI) branch on cause
without string-matching messages.

The trust-envelope failures (``SignatureInvalid``, ``PayloadHashMismatch``,
``CanonicalizationFailed``, ``LedgerIntegrityError``) belong to the shared envelope and
live in ``avow.errors``; they are re-exported here so the score face's callers keep a
single import site.

``ReplayRefused`` is the score face's own, and stays here: ``assay.replay`` means
"recompute this receipt from its inputs and check it reproduces", which is a scoring
concept. The envelope's word for a bad hash is ``PayloadHashMismatch`` — the envelope
detects no replay of any kind."""

from __future__ import annotations

from typing import ClassVar

from avow.errors import (
    CanonicalizationFailed,
    LedgerIntegrityError,
    PayloadHashMismatch,
    ReplayMismatch,
    SignatureInvalid,
)

__all__ = [
    "AssayError",
    "CanonicalizationFailed",
    "EmptyRelevantSet",
    "InsufficientSamples",
    "InvalidAgreementRequest",
    "InvalidRankingRequest",
    "InvalidScoreRequest",
    "LedgerIntegrityError",
    "PayloadHashMismatch",
    "ReplayMismatch",
    "ReplayRefused",
    "ScoringExtraMissing",
    "SignatureInvalid",
    "UnknownMetric",
]


class AssayError(Exception):
    """Base class for every Assay scoring-face domain error."""

    code: ClassVar[str] = "assay.error"


class InvalidScoreRequest(AssayError):
    """Inputs are malformed (length mismatch, empty, single-class)."""

    code: ClassVar[str] = "assay.invalid_request"


class UnknownMetric(AssayError):
    """Requested metric name is not registered."""

    code: ClassVar[str] = "assay.unknown_metric"


class InvalidRankingRequest(AssayError):
    """A ranked-retrieval input cannot be scored as given.

    Covers ``k <= 0``, an empty ranked list, the same document twice in one ranked list
    or judged twice in one query, a negative relevance gain, and an empty query set.
    Each of these makes some metric's answer undefined rather than merely small, so the
    face refuses instead of returning a number whose meaning nobody could state."""

    code: ClassVar[str] = "assay.invalid_ranking_request"


class EmptyRelevantSet(AssayError):
    """No document is judged relevant, so recall and nDCG have no denominator.

    Returning 0.0 here would read as "the ranker found nothing" and blame the ranker for
    missing *judgments*. Those are different failures with different fixes, so they get
    different answers: a real 0.0 when the ranker misses, a refusal when nobody judged."""

    code: ClassVar[str] = "assay.empty_relevant_set"


class InvalidAgreementRequest(AssayError):
    """An inter-rater input cannot be scored as given.

    Covers two raters who graded different numbers of items, an empty item set, a band
    that is not on the declared scale, a scale with fewer than two levels or a repeated
    one, and the same item graded twice. Each of these either makes the answer undefined
    or — worse — has scikit-learn quietly discard the offending rows and return a
    healthy-looking number computed over fewer items than the caller handed in."""

    code: ClassVar[str] = "assay.invalid_agreement_request"


class InsufficientSamples(AssayError):
    """Sample count is below the abstention floor."""

    code: ClassVar[str] = "assay.insufficient_samples"


class ScoringExtraMissing(AssayError):
    """The scoring face was imported without its heavy extra installed."""

    code: ClassVar[str] = "assay.scoring_extra_missing"


class ReplayRefused(AssayError):
    """``assay.replay`` cannot reproduce this receipt, so it refuses to answer.

    "Replay" here is the *scoring* sense — recompute the payload from the request and
    check it reproduces — not the cryptographic one. A receipt that records no
    determinism settings is not one this can recompute, so it fails explicitly rather
    than returning ``False`` and reading as a mismatch it never actually measured."""

    code: ClassVar[str] = "assay.replay_refused"
