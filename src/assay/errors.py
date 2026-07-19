"""Coded domain-error catalog. Every failure raises a typed AssayError with a
stable string ``code`` so callers (and the CLI) can branch on cause without
string-matching messages."""

from __future__ import annotations

from typing import ClassVar


class AssayError(Exception):
    """Base class for every Assay domain error."""

    code: ClassVar[str] = "assay.error"


class InvalidScoreRequest(AssayError):
    """Inputs are malformed (length mismatch, empty, single-class)."""

    code: ClassVar[str] = "assay.invalid_request"


class UnknownMetric(AssayError):
    """Requested metric name is not registered."""

    code: ClassVar[str] = "assay.unknown_metric"


class InsufficientSamples(AssayError):
    """Sample count is below the abstention floor."""

    code: ClassVar[str] = "assay.insufficient_samples"


class CanonicalizationFailed(AssayError):
    """Payload could not be canonicalized to RFC 8785 JCS bytes."""

    code: ClassVar[str] = "assay.canonicalization_failed"


class SignatureInvalid(AssayError):
    """Ed25519 signature does not match the payload."""

    code: ClassVar[str] = "assay.signature_invalid"


class ReplayMismatch(AssayError):
    """Recomputed content-hash does not match the receipt's stored hash."""

    code: ClassVar[str] = "assay.replay_mismatch"


class LedgerIntegrityError(AssayError):
    """A ledger entry's stored hash disagrees with its recomputed hash."""

    code: ClassVar[str] = "assay.ledger_integrity"
