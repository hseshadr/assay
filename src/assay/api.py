"""The Assay facade: score, composite_score, verify, replay.

This is the only module most callers touch. It wires the reused primitives into a
signed, reproducible receipt and offers offline verification and replay."""

from __future__ import annotations

from nacl.signing import SigningKey

from assay import __version__
from assay.calibration import CalibrationReport, calibration_report
from assay.canonical import content_hash
from assay.composite import SubScore, composite
from assay.errors import ReplayMismatch, SignatureInvalid
from assay.metrics import ClassificationScores, binary_scores, correctness
from assay.models import CompositeRequest, ScoreRequest, SubScoreInput
from assay.receipt import (
    CalibrationDetail,
    ClassificationDetail,
    CompositeDetail,
    ReceiptPayload,
    ReliabilityPoint,
    ScoreReceipt,
    SubScorePart,
    payload_digest,
    sign_payload,
)
from assay.settings import AssaySettings
from assay.uncertainty import Abstention, Estimate, mean_interval
from assay.verify import verify_receipt


def _classification_detail(scores: ClassificationScores) -> ClassificationDetail:
    return ClassificationDetail(
        precision=scores.precision,
        recall=scores.recall,
        f1=scores.f1,
        pr_auc=scores.pr_auc,
        roc_auc=scores.roc_auc,
    )


def _calibration_detail(report: CalibrationReport) -> CalibrationDetail:
    points = tuple(
        ReliabilityPoint(
            mean_predicted=b.mean_predicted,
            fraction_positive=b.fraction_positive,
            count=b.count,
        )
        for b in report.bins
    )
    return CalibrationDetail(ece=report.ece, brier=report.brier, reliability=points)


def _headline(
    estimate: Estimate,
) -> tuple[float | None, float | None, float | None, bool]:
    if isinstance(estimate, Abstention):
        return None, None, None, True
    return estimate.point, estimate.low, estimate.high, False


def _estimate(request: ScoreRequest, settings: AssaySettings) -> Estimate:
    hits = correctness(request.y_true, request.y_score, threshold=request.threshold)
    return mean_interval(
        hits,
        min_samples=settings.min_samples,
        n_resamples=settings.bootstrap_resamples,
        confidence_level=settings.confidence_level,
        seed=settings.bootstrap_seed,
    )


def _classification_payload(request: ScoreRequest, settings: AssaySettings) -> ReceiptPayload:
    scores = binary_scores(request.y_true, request.y_score, threshold=request.threshold)
    report = calibration_report(request.y_true, request.y_score, n_bins=settings.ece_bins)
    point, low, high, abstained = _headline(_estimate(request, settings))
    return ReceiptPayload(
        assay_version=__version__,
        metric=request.metric,
        metric_version=request.metric_version,
        inputs_hash=content_hash(request.model_dump(mode="json")),
        score=point,
        interval_low=low,
        interval_high=high,
        abstained=abstained,
        classification=_classification_detail(scores),
        calibration=_calibration_detail(report),
    )


def score(
    request: ScoreRequest, *, signing_key: SigningKey, settings: AssaySettings
) -> ScoreReceipt:
    """Score a classification request into a signed, verifiable receipt."""
    return sign_payload(_classification_payload(request, settings), signing_key)


def _as_subscore(s: SubScoreInput) -> SubScore:
    return SubScore(
        name=s.name,
        value=s.value,
        low=s.low,
        high=s.high,
        scale_min=s.scale_min,
        scale_max=s.scale_max,
        weight=s.weight,
    )


def _composite_payload(request: CompositeRequest) -> ReceiptPayload:
    result = composite([_as_subscore(s) for s in request.subscores])
    parts = tuple(
        SubScorePart(name=p.name, normalized_value=p.normalized_value, weight=p.weight)
        for p in result.parts
    )
    return ReceiptPayload(
        assay_version=__version__,
        metric=request.metric,
        metric_version=request.metric_version,
        inputs_hash=content_hash(request.model_dump(mode="json")),
        score=result.value,
        interval_low=result.low,
        interval_high=result.high,
        composite=CompositeDetail(parts=parts),
    )


def composite_score(request: CompositeRequest, *, signing_key: SigningKey) -> ScoreReceipt:
    """Score a weighted multi-scale composite into a signed receipt."""
    return sign_payload(_composite_payload(request), signing_key)


def verify(receipt: ScoreReceipt) -> bool:
    """Return whether a receipt verifies offline (signature + hash)."""
    try:
        verify_receipt(receipt)
    except (SignatureInvalid, ReplayMismatch):
        return False
    return True


def replay(request: ScoreRequest, receipt: ScoreReceipt, *, settings: AssaySettings) -> bool:
    """Recompute the payload from inputs and confirm it reproduces the signed hash."""
    recomputed = _classification_payload(request, settings)
    return payload_digest(recomputed) == receipt.payload_hash
