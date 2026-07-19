from __future__ import annotations

from nacl.signing import SigningKey

from assay.api import replay, score, verify
from assay.models import ScoreRequest
from assay.settings import AssaySettings

_SEED = bytes(range(32))
_KEY = SigningKey(_SEED)


def _classification_request() -> ScoreRequest:
    return ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=tuple([0, 1] * 20),
        y_score=tuple([0.2, 0.8] * 20),
    )


def _settings() -> AssaySettings:
    return AssaySettings()


def test_case1_should_reproduce_identical_score_and_hash_for_same_inputs() -> None:
    # Given the same request, metric version and key
    request = _classification_request()
    # When scored twice
    first = score(request, signing_key=_KEY, settings=_settings())
    second = score(request, signing_key=_KEY, settings=_settings())
    # Then the score and the receipt content-hash are identical
    assert first.payload.score == second.payload.score
    assert first.payload_hash == second.payload_hash
    assert first == second


def test_case2_should_verify_offline_and_recompute_the_score() -> None:
    # Given a signed receipt and its original request
    request = _classification_request()
    receipt = score(request, signing_key=_KEY, settings=_settings())
    # When verified offline and replayed from the same inputs
    verified = verify(receipt)
    replayed = replay(request, receipt, settings=_settings())
    # Then the signature is valid and the score recomputes to the same value
    assert verified is True
    assert replayed is True


def test_case3_should_fail_verification_when_receipt_is_tampered() -> None:
    # Given a valid receipt
    receipt = score(_classification_request(), signing_key=_KEY, settings=_settings())
    # When the signed score is altered without re-signing
    swapped = receipt.payload.model_copy(update={"score": 0.123})
    tampered = receipt.model_copy(update={"payload": swapped})
    # Then verification fails (hash no longer matches the payload)
    assert verify(tampered) is False
    # And a blanked signature also fails
    forged = receipt.model_copy(update={"signature": "11" * 64})
    assert verify(forged) is False


def test_case4_should_abstain_and_not_fabricate_a_point_when_sample_is_thin() -> None:
    # Given only five samples with the default floor of 30
    thin = ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=(0, 1, 0, 1, 0),
        y_score=(0.2, 0.8, 0.3, 0.7, 0.4),
    )
    # When scored
    receipt = score(thin, signing_key=_KEY, settings=_settings())
    # Then it abstains — no point number, no interval (never a fabricated value)
    assert receipt.payload.abstained is True
    assert receipt.payload.score is None
    assert receipt.payload.interval_low is None
    assert receipt.payload.interval_high is None
