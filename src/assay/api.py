"""The Assay facade: score, composite_score, ranking_score, agreement_score, verify, replay.

This is the only module most callers touch. It wires the reused primitives into a
signed, reproducible receipt and offers offline verification and replay."""

from __future__ import annotations

from nacl.signing import SigningKey

from assay.agreement import AgreementReport, agreement_report
from assay.calibration import CalibrationReport, calibration_report
from assay.composite import SubScore, composite
from assay.errors import (
    CanonicalizationFailed,
    InsufficientSamples,
    PayloadHashMismatch,
    ReplayRefused,
    SignatureInvalid,
    UnknownMetric,
)
from assay.metrics import ClassificationScores, ConfusionCounts, binary_scores, correctness
from assay.models import (
    AgreementRequest,
    CompositeRequest,
    RankingRequest,
    ScoreRequest,
    SubScoreInput,
)
from assay.ranking import RankingReport, ranking_report
from assay.receipt import (
    AgreementDetail,
    CalibrationDetail,
    ClassificationDetail,
    CompositeDetail,
    ConfusionDetail,
    DeterminismSettings,
    RankingDetail,
    ReceiptPayload,
    ReliabilityPoint,
    ScoreReceipt,
    SubScorePart,
    payload_digest,
    sign_payload,
)
from assay.settings import AssaySettings
from assay.uncertainty import Abstention, Estimate, mean_interval
from avow import __version__
from avow.canonical import content_hash
from avow.verify import verify_receipt

# The metric label a caller names is not free text: it selects which computation
# Assay performs and is signed into the receipt. Only registered metrics are
# accepted, so a receipt's `metric` field is verified, never merely asserted.
_CLASSIFICATION_METRICS = frozenset({"binary"})
_COMPOSITE_METRICS = frozenset({"weighted_composite"})
_RANKING_METRICS = frozenset({"ranking"})
_AGREEMENT_METRICS = frozenset({"agreement"})


def _require_metric(name: str, allowed: frozenset[str]) -> None:
    if name not in allowed:
        raise UnknownMetric(f"unknown metric {name!r}")


def _confusion_detail(counts: ConfusionCounts) -> ConfusionDetail:
    return ConfusionDetail(
        true_positives=counts.true_positives,
        false_positives=counts.false_positives,
        true_negatives=counts.true_negatives,
        false_negatives=counts.false_negatives,
    )


def _classification_detail(scores: ClassificationScores) -> ClassificationDetail:
    return ClassificationDetail(
        precision=scores.precision,
        recall=scores.recall,
        f1=scores.f1,
        false_negative_rate=scores.false_negative_rate,
        pr_auc=scores.pr_auc,
        roc_auc=scores.roc_auc,
        confusion=_confusion_detail(scores.counts),
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


def _determinism(settings: AssaySettings) -> DeterminismSettings:
    """The determinism-affecting settings, recorded into the signed payload."""
    return DeterminismSettings(
        min_samples=settings.min_samples,
        bootstrap_resamples=settings.bootstrap_resamples,
        confidence_level=settings.confidence_level,
        ece_bins=settings.ece_bins,
        bootstrap_seed=settings.bootstrap_seed,
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
        abstain_reason=InsufficientSamples.code if abstained else None,
        determinism=_determinism(settings),
        classification=_classification_detail(scores),
        calibration=_calibration_detail(report),
    )


def score(
    request: ScoreRequest, *, signing_key: SigningKey, settings: AssaySettings
) -> ScoreReceipt:
    """Score a classification request into a signed, verifiable receipt."""
    _require_metric(request.metric, _CLASSIFICATION_METRICS)
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
    _require_metric(request.metric, _COMPOSITE_METRICS)
    return sign_payload(_composite_payload(request), signing_key)


def _ranking_detail(report: RankingReport) -> RankingDetail:
    return RankingDetail(
        k=report.k,
        n_queries=report.n_queries,
        mean_precision_at_k=report.mean_precision_at_k,
        mean_recall_at_k=report.mean_recall_at_k,
        mean_f1_at_k=report.mean_f1_at_k,
        mean_ndcg_at_k=report.mean_ndcg_at_k,
        mrr=report.mrr,
        mean_average_precision=report.mean_average_precision,
    )


def _ranking_payload(request: RankingRequest, settings: AssaySettings) -> ReceiptPayload:
    report = ranking_report(request.queries, settings=settings, k=request.k)
    point, low, high, abstained = _headline(report.ndcg_interval)
    return ReceiptPayload(
        assay_version=__version__,
        metric=request.metric,
        metric_version=request.metric_version,
        inputs_hash=content_hash(request.model_dump(mode="json")),
        score=point,
        interval_low=low,
        interval_high=high,
        abstained=abstained,
        abstain_reason=InsufficientSamples.code if abstained else None,
        determinism=_determinism(settings),
        ranking=_ranking_detail(report),
    )


def ranking_score(
    request: RankingRequest, *, signing_key: SigningKey, settings: AssaySettings
) -> ScoreReceipt:
    """Score a ranked-retrieval query set into a signed, verifiable receipt.

    The headline ``score`` is mean nDCG@k with its bootstrap interval — or an abstention
    when the query set is smaller than the sample floor. The per-query means are always
    carried in ``payload.ranking``, so a report that cannot support an interval still
    says what it measured."""
    _require_metric(request.metric, _RANKING_METRICS)
    return sign_payload(_ranking_payload(request, settings), signing_key)


def _agreement_detail(report: AgreementReport) -> AgreementDetail:
    return AgreementDetail(
        scale=report.scale,
        n_items=report.n_items,
        n_exact_matches=report.n_exact_matches,
        percent_agreement=report.percent_agreement,
        weighted_agreement=report.weighted_agreement,
        quadratic_kappa=report.quadratic_kappa,
        kendall_tau_b=report.kendall_tau_b,
    )


def _agreement_payload(request: AgreementRequest, settings: AssaySettings) -> ReceiptPayload:
    report = agreement_report(request.ratings, scale=request.scale, settings=settings)
    point, low, high, abstained = _headline(report.weighted_agreement_interval)
    return ReceiptPayload(
        assay_version=__version__,
        metric=request.metric,
        metric_version=request.metric_version,
        inputs_hash=content_hash(request.model_dump(mode="json")),
        score=point,
        interval_low=low,
        interval_high=high,
        abstained=abstained,
        abstain_reason=InsufficientSamples.code if abstained else None,
        determinism=_determinism(settings),
        agreement=_agreement_detail(report),
    )


def agreement_score(
    request: AgreementRequest, *, signing_key: SigningKey, settings: AssaySettings
) -> ScoreReceipt:
    """Score inter-rater agreement into a signed, verifiable receipt.

    The headline ``score`` is the mean per-item weighted agreement with its bootstrap
    interval — or an abstention when there are fewer items than the sample floor. Kappa
    is deliberately NOT the headline: it is not the mean of any per-item quantity, so no
    bootstrap of a mean can put an interval on it. It is carried in ``payload.agreement``
    alongside tau-b and the declared band order, which is signed in with them because the
    same ratings against a reordered scale are a different measurement."""
    _require_metric(request.metric, _AGREEMENT_METRICS)
    return sign_payload(_agreement_payload(request, settings), signing_key)


def verify(receipt: ScoreReceipt, *, expected_public_key: str) -> bool:
    """Return whether a receipt verifies offline against a **pinned** signer.

    ``expected_public_key`` is the signer's public key the caller trusts, obtained
    out-of-band (e.g. the ``.pub`` file from ``keygen``) — never read from the
    receipt itself, whose embedded key an attacker could swap."""
    try:
        verify_receipt(receipt, expected_public_key=expected_public_key)
    except (SignatureInvalid, PayloadHashMismatch, CanonicalizationFailed):
        return False
    return True


def _settings_for_replay(determinism: DeterminismSettings | None) -> AssaySettings:
    """Rebuild the settings a classification receipt was computed under, from what it
    recorded. A receipt that records none is not one this can reproduce, so we fail
    explicitly rather than silently returning a mismatch."""
    if determinism is None:
        raise ReplayRefused("receipt records no determinism settings to replay")
    return AssaySettings(
        min_samples=determinism.min_samples,
        bootstrap_resamples=determinism.bootstrap_resamples,
        confidence_level=determinism.confidence_level,
        ece_bins=determinism.ece_bins,
        bootstrap_seed=determinism.bootstrap_seed,
    )


def replay(request: ScoreRequest, receipt: ScoreReceipt) -> bool:
    """Recompute the payload from the request AND the settings recorded IN the receipt,
    then confirm it reproduces the receipt's actual payload.

    Unconditional: no ambient settings need to match, because the determinism-affecting
    settings are signed into the receipt. A receipt computed under different settings is
    a *different, explicitly-recorded* receipt — never a silent replay failure.

    The comparison is against a digest re-derived from ``receipt.payload`` — the same
    ``payload_digest`` the envelope's own hash check uses — and NOT against the
    ``payload_hash`` field alone. A payload edited behind a stale hash field would
    otherwise replay clean, because that check measures the label, not the content it
    labels. The stored hash must agree too, so a self-inconsistent receipt never replays."""
    settings = _settings_for_replay(receipt.payload.determinism)
    recomputed = payload_digest(_classification_payload(request, settings))
    return recomputed == payload_digest(receipt.payload) == receipt.payload_hash
