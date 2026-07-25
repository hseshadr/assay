"""The score face's receipt subjects, carried by the shared ``avow`` envelope.

This module defines only the *scoring* subject models (what a number is) and the
concrete ``ScoreReceipt`` alias. The envelope itself — ``SignedReceipt``,
``sign_payload``, ``verify_signature``, ``payload_digest`` — lives in ``avow`` and is
re-exported here for callers that reach for the score face's receipt surface directly.
The envelope signs these subjects without ever inspecting their fields."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from avow.envelope import (
    SignedReceipt,
    payload_digest,
    sign_payload,
    verify_signature,
)


class ReliabilityPoint(BaseModel):
    """One reliability-diagram point, as stored in a receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mean_predicted: float
    fraction_positive: float
    count: int


class ClassificationDetail(BaseModel):
    """Point classification metrics carried in a receipt.

    F1, precision and recall are first-class here alongside the ranking metrics —
    accuracy alone never speaks for a classifier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    precision: float
    recall: float
    f1: float
    pr_auc: float
    roc_auc: float


class CalibrationDetail(BaseModel):
    """Calibration evidence carried in a receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ece: float
    brier: float
    reliability: tuple[ReliabilityPoint, ...]


class SubScorePart(BaseModel):
    """One normalized composite part carried in a receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    normalized_value: float
    weight: float


class CompositeDetail(BaseModel):
    """Composite breakdown carried in a receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parts: tuple[SubScorePart, ...]


class DeterminismSettings(BaseModel):
    """The settings that determine a classification receipt's numbers, recorded INSIDE
    the signed payload so replay is unconditional.

    ``inputs_hash`` covers only the request, but the score, interval and ECE also depend
    on these knobs. Signing them here means anyone can recompute from the request plus
    THESE settings and reproduce the receipt — no ambient environment has to match — and
    a receipt computed under different knobs is explicitly different, never a silent
    replay failure. Composite receipts leave this ``None``: they read no settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_samples: int
    bootstrap_resamples: int
    confidence_level: float
    ece_bins: int
    bootstrap_seed: int


class ReceiptPayload(BaseModel):
    """The deterministic, signable content of a score receipt (no wall-clock time).

    This is the *subject* the score face fills; the ``avow`` envelope signs it without
    knowing what it carries, which is why the effect face can reuse the same envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assay_version: str
    metric: str
    metric_version: str
    inputs_hash: str
    score: float | None
    interval_low: float | None = None
    interval_high: float | None = None
    abstained: bool = False
    abstain_reason: str | None = None
    determinism: DeterminismSettings | None = None
    classification: ClassificationDetail | None = None
    calibration: CalibrationDetail | None = None
    composite: CompositeDetail | None = None


# The score face's concrete envelope. ``ScoreReceipt`` stays the public name callers
# import; it is ``SignedReceipt`` parametrized with the score subject.
ScoreReceipt = SignedReceipt[ReceiptPayload]

__all__ = [
    "CalibrationDetail",
    "ClassificationDetail",
    "CompositeDetail",
    "DeterminismSettings",
    "ReceiptPayload",
    "ReliabilityPoint",
    "ScoreReceipt",
    "SignedReceipt",
    "SubScorePart",
    "payload_digest",
    "sign_payload",
    "verify_signature",
]
