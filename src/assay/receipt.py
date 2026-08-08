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


class ConfusionDetail(BaseModel):
    """The four confusion cells at the scored threshold, carried in a receipt.

    Named cells rather than a bare 2x2 array, because the order they come back in from
    a confusion matrix is ``tn, fp, fn, tp`` and reading that tuple in the wrong order
    swaps a miss for a false alarm without changing a single total."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


class ClassificationDetail(BaseModel):
    """Point classification metrics carried in a receipt.

    F1, precision and recall are first-class here alongside the ranking metrics —
    accuracy alone never speaks for a classifier. ``false_negative_rate`` is carried by
    name even though it is ``1 - recall``: for a screening system the miss is the number
    it is judged on, and nobody reads a 3% miss rate off a recall of 0.97."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    precision: float
    recall: float
    f1: float
    false_negative_rate: float
    pr_auc: float
    roc_auc: float
    confusion: ConfusionDetail


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


class RankingDetail(BaseModel):
    """Ranked-retrieval evidence carried in a receipt.

    ``k`` is recorded alongside the numbers because "precision 0.6" means nothing without
    it. The per-query rows stay out of the receipt deliberately: they carry document ids
    from the caller's catalog, and a receipt is meant to be shareable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    k: int
    n_queries: int
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_f1_at_k: float
    mean_ndcg_at_k: float
    mrr: float
    mean_average_precision: float


class AgreementDetail(BaseModel):
    """Inter-rater agreement evidence carried in a receipt.

    ``scale`` rides along because the numbers are meaningless without the band order
    they were computed under — the same ratings against a reordered scale are a
    different measurement. ``quadratic_kappa`` and ``kendall_tau_b`` are ``None`` when
    the ratings were too degenerate for the statistic to exist. The per-item rows stay
    out, as the ranking rows do: they carry the caller's item ids, and a receipt is
    meant to be shareable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scale: tuple[str, ...]
    n_items: int
    n_exact_matches: int
    percent_agreement: float
    weighted_agreement: float
    quadratic_kappa: float | None = None
    kendall_tau_b: float | None = None


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
    ranking: RankingDetail | None = None
    agreement: AgreementDetail | None = None


# The score face's concrete envelope. ``ScoreReceipt`` stays the public name callers
# import; it is ``SignedReceipt`` parametrized with the score subject.
ScoreReceipt = SignedReceipt[ReceiptPayload]

__all__ = [
    "AgreementDetail",
    "CalibrationDetail",
    "ClassificationDetail",
    "CompositeDetail",
    "ConfusionDetail",
    "DeterminismSettings",
    "RankingDetail",
    "ReceiptPayload",
    "ReliabilityPoint",
    "ScoreReceipt",
    "SignedReceipt",
    "SubScorePart",
    "payload_digest",
    "sign_payload",
    "verify_signature",
]
