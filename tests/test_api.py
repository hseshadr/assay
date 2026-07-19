from __future__ import annotations

from nacl.signing import SigningKey

from assay.api import composite_score, replay, score, verify
from assay.models import CompositeRequest, ScoreRequest, SubScoreInput
from assay.settings import AssaySettings

_SEED = bytes(range(32))
_KEY = SigningKey(_SEED)


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
    assert verify(receipt) is True
    assert receipt.payload.score == 1.0
    assert receipt.payload.abstained is False
    assert receipt.payload.calibration is not None
    assert replay(request, receipt, settings=AssaySettings()) is True


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
    # Then the headline score is withheld (no fake point number)
    assert receipt.payload.abstained is True
    assert receipt.payload.score is None
    assert receipt.payload.interval_low is None


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
    assert verify(receipt) is True
    assert receipt.payload.score == 0.8
    assert receipt.payload.interval_low == 0.7
    assert receipt.payload.interval_high == 0.9
