from __future__ import annotations

import pytest
from nacl.signing import SigningKey

from assay.api import composite_score, replay, score, verify
from assay.errors import InsufficientSamples, ReplayMismatch, UnknownMetric
from assay.models import CompositeRequest, ScoreRequest, SubScoreInput
from assay.receipt import sign_payload
from assay.settings import AssaySettings

_SEED = bytes(range(32))
_KEY = SigningKey(_SEED)
_EXPECTED = bytes(_KEY.verify_key).hex()


def _classification_request() -> ScoreRequest:
    # 40 samples, perfectly separated at 0.2/0.8 → deterministic, above the floor
    y_true = [0, 1] * 20
    y_score = [0.2, 0.8] * 20
    return ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=tuple(y_true),
        y_score=tuple(y_score),
    )


def test_should_produce_and_verify_a_classification_receipt() -> None:
    # Given a classification request above the sample floor
    request = _classification_request()
    # When scored and verified
    receipt = score(request, signing_key=_KEY, settings=AssaySettings())
    # Then it verifies, carries the accuracy point, and an interval
    assert verify(receipt, expected_public_key=_EXPECTED) is True
    assert receipt.payload.score == 1.0
    assert receipt.payload.abstained is False
    assert receipt.payload.calibration is not None
    assert replay(request, receipt) is True


def _mixed_request() -> ScoreRequest:
    # 40 samples above the floor, only 30/40 correct, so the confidence interval genuinely
    # depends on the determinism-affecting settings (a perfectly separated set has a
    # degenerate interval that would hide the settings dependence this test exposes).
    y_true = tuple([0] * 20 + [1] * 20)
    y_score = tuple([0.2] * 15 + [0.8] * 5 + [0.8] * 15 + [0.2] * 5)
    return ScoreRequest(metric="binary", metric_version="1", y_true=y_true, y_score=y_score)


def test_replay_is_unconditional_and_records_the_determinism_settings() -> None:
    request = _mixed_request()
    # Sealed under a specific determinism-affecting setting (the confidence level)
    receipt = score(request, signing_key=_KEY, settings=AssaySettings(confidence_level=0.95))
    # The receipt records the exact settings it was computed under — explicit and signed
    assert receipt.payload.determinism is not None
    assert receipt.payload.determinism.confidence_level == 0.95
    # Replay recomputes from the request + the RECORDED settings, so it reproduces
    # unconditionally: no ambient AssaySettings has to be threaded back in
    assert replay(request, receipt) is True


def test_changed_env_is_explicit_in_the_receipt_not_a_silent_replay_failure() -> None:
    request = _mixed_request()
    tight = score(request, signing_key=_KEY, settings=AssaySettings(confidence_level=0.95))
    wide = score(request, signing_key=_KEY, settings=AssaySettings(confidence_level=0.80))
    # A determinism-affecting change yields a DIFFERENT receipt whose recorded settings
    # make the difference explicit — not a silent replay mismatch
    assert tight.payload.determinism != wide.payload.determinism
    assert tight.payload_hash != wide.payload_hash
    # ...yet each still replays against ITS OWN recorded settings, unconditionally
    assert replay(request, tight) is True
    assert replay(request, wide) is True
    # A change to an IRRELEVANT setting (the ledger path) does not change the receipt
    moved = score(
        request,
        signing_key=_KEY,
        settings=AssaySettings(confidence_level=0.95, ledger_path="somewhere-else.jsonl"),
    )
    assert moved.payload_hash == tight.payload_hash


def test_replay_refuses_a_receipt_that_records_no_determinism_settings() -> None:
    # Given a classification receipt with no recorded determinism settings (produced
    # before the settings were signed in, or carrying a non-classification subject)
    request = _mixed_request()
    receipt = score(request, signing_key=_KEY, settings=AssaySettings())
    stripped = sign_payload(receipt.payload.model_copy(update={"determinism": None}), _KEY)
    # Then replay refuses it explicitly rather than silently reporting a mismatch
    with pytest.raises(ReplayMismatch):
        replay(request, stripped)


def test_replay_should_reject_a_payload_edited_behind_a_stale_hash() -> None:
    # Given a genuine receipt whose PAYLOAD was edited (score -> 0.99) while its
    # self-reported payload_hash field was left untouched — the cheapest possible tamper,
    # and the one a replay that compares against that field cannot see.
    request = _classification_request()
    receipt = score(request, signing_key=_KEY, settings=AssaySettings())
    tampered = receipt.model_copy(
        update={"payload": receipt.payload.model_copy(update={"score": 0.99})}
    )
    assert tampered.payload.score == 0.99
    assert tampered.payload_hash == receipt.payload_hash  # stale label, edited content
    # Then verification rejects it...
    assert verify(tampered, expected_public_key=_EXPECTED) is False
    # ...and so must replay: "these inputs reproduce this receipt" is a claim about the
    # payload, never about the hash the payload carries alongside itself.
    assert replay(request, tampered) is False


def test_should_reject_a_forgery_resigned_with_an_attacker_key() -> None:
    # Given a genuine receipt from the honest signer, pinned out-of-band
    receipt = score(_classification_request(), signing_key=_KEY, settings=AssaySettings())
    # When an attacker flips the signed score, re-signs with their OWN key, and
    # swaps in their own public key (probe-1 forgery)
    attacker = SigningKey(bytes(range(1, 33)))
    forged_payload = receipt.payload.model_copy(update={"score": 0.123})
    forgery = sign_payload(forged_payload, attacker)
    # Then pinned verification returns False — authenticity is not fooled
    assert verify(forgery, expected_public_key=_EXPECTED) is False


def test_should_return_false_when_signature_hex_is_malformed() -> None:
    # Given a receipt whose signature is not valid hex ("zz")
    receipt = score(_classification_request(), signing_key=_KEY, settings=AssaySettings())
    bad = receipt.model_copy(update={"signature": "zz"})
    # When verified through the bool facade
    # Then it fails closed (False), not a raw ValueError traceback
    assert verify(bad, expected_public_key=_EXPECTED) is False


def test_should_abstain_below_the_sample_floor() -> None:
    # Given only 5 samples with a floor of 30
    request = ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=(0, 1, 0, 1, 0),
        y_score=(0.2, 0.8, 0.3, 0.7, 0.4),
    )
    # When scored
    receipt = score(request, signing_key=_KEY, settings=AssaySettings())
    # Then the headline score is withheld (no fake point number) and the receipt
    # carries the coded reason for abstaining, so *why* is verifiable, not asserted
    assert receipt.payload.abstained is True
    assert receipt.payload.score is None
    assert receipt.payload.interval_low is None
    assert receipt.payload.abstain_reason == InsufficientSamples.code


def test_should_not_set_an_abstain_reason_when_a_point_is_emitted() -> None:
    # Given a request above the sample floor
    receipt = score(_classification_request(), signing_key=_KEY, settings=AssaySettings())
    # Then no abstain reason is carried
    assert receipt.payload.abstained is False
    assert receipt.payload.abstain_reason is None


def test_should_reject_an_unknown_classification_metric() -> None:
    # Given a request naming a metric Assay does not implement
    request = ScoreRequest(
        metric="frobnicate",
        metric_version="1",
        y_true=tuple([0, 1] * 20),
        y_score=tuple([0.2, 0.8] * 20),
    )
    # When scored
    # Then it is rejected with a coded UnknownMetric before anything is signed
    with pytest.raises(UnknownMetric):
        score(request, signing_key=_KEY, settings=AssaySettings())


def test_should_reject_an_unknown_composite_metric() -> None:
    # Given a composite request whose metric label is unknown
    subs = tuple(
        SubScoreInput(
            name=n, value=0.5, low=0.4, high=0.6, scale_min=0.0, scale_max=1.0, weight=1.0
        )
        for n in ("a", "b", "c")
    )
    request = CompositeRequest(metric="mystery", metric_version="1", subscores=subs)
    # When scored
    # Then it is rejected with a coded UnknownMetric
    with pytest.raises(UnknownMetric):
        composite_score(request, signing_key=_KEY)


def test_should_verify_a_composite_receipt_with_propagated_interval() -> None:
    # Given a 3-scale composite request
    subs = (
        SubScoreInput(
            name="accuracy",
            value=0.9,
            low=0.85,
            high=0.95,
            scale_min=0.0,
            scale_max=1.0,
            weight=1.0,
        ),
        SubScoreInput(
            name="latency",
            value=80.0,
            low=70.0,
            high=90.0,
            scale_min=0.0,
            scale_max=100.0,
            weight=1.0,
        ),
        SubScoreInput(
            name="rating",
            value=4.0,
            low=3.5,
            high=4.5,
            scale_min=1.0,
            scale_max=5.0,
            weight=2.0,
        ),
    )
    request = CompositeRequest(metric_version="1", subscores=subs)
    # When scored and verified
    receipt = composite_score(request, signing_key=_KEY)
    # Then it verifies and carries the propagated composite interval
    assert verify(receipt, expected_public_key=_EXPECTED) is True
    assert receipt.payload.score == 0.8
    assert receipt.payload.interval_low == 0.7
    assert receipt.payload.interval_high == 0.9
