"""Assay demo: proves all six v0 acceptance cases end-to-end.

Run it:  uv run python demo/run_demo.py
Every case computes a real score, signs a real receipt, and asserts the honesty
property that case guarantees."""

from __future__ import annotations

import math

from nacl.signing import SigningKey

from assay.api import composite_score, replay, score, verify
from assay.models import CompositeRequest, ScoreRequest, SubScoreInput
from assay.receipt import sign_payload
from assay.settings import AssaySettings

_SEED = bytes(range(32))


def _pubkey(key: SigningKey) -> str:
    """The signer's public key, pinned by the verifier out-of-band."""
    return bytes(key.verify_key).hex()


def _big_request() -> ScoreRequest:
    return ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=tuple([0, 1] * 20),
        y_score=tuple([0.2, 0.8] * 20),
    )


def _composite_request() -> CompositeRequest:
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
    return CompositeRequest(metric_version="1", subscores=subs)


def _case_reproducible(key: SigningKey, settings: AssaySettings) -> None:
    a = score(_big_request(), signing_key=key, settings=settings)
    b = score(_big_request(), signing_key=key, settings=settings)
    assert a.payload_hash == b.payload_hash and a == b
    print(f"[1] reproducible: identical hash {a.payload_hash[:23]}...")


def _case_offline_verify(key: SigningKey, settings: AssaySettings) -> None:
    receipt = score(_big_request(), signing_key=key, settings=settings)
    assert verify(receipt, expected_public_key=_pubkey(key)) is True
    assert replay(_big_request(), receipt, settings=settings) is True
    print("[2] offline verify + replay: signature valid, score recomputes")


def _case_tamper(key: SigningKey, settings: AssaySettings) -> None:
    receipt = score(_big_request(), signing_key=key, settings=settings)
    expected = _pubkey(key)
    # A blanked signature fails against the pinned signer.
    forged = receipt.model_copy(update={"signature": "00" * 64})
    assert verify(forged, expected_public_key=expected) is False
    # A re-signed forgery (attacker flips the score, signs with their OWN key and
    # swaps in their pubkey) is also rejected — authenticity is pinned, not trusted.
    attacker = SigningKey(bytes(range(1, 33)))
    resigned = sign_payload(receipt.payload.model_copy(update={"score": 0.999}), attacker)
    assert verify(resigned, expected_public_key=expected) is False
    print("[3] tamper + forgery detected: neither a flipped sig nor a re-signed key passes")


def _case_abstain(key: SigningKey, settings: AssaySettings) -> None:
    thin = ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=(0, 1, 0, 1, 0),
        y_score=(0.2, 0.8, 0.3, 0.7, 0.4),
    )
    receipt = score(thin, signing_key=key, settings=settings)
    assert receipt.payload.abstained is True and receipt.payload.score is None
    print("[4] low sample: abstained, no fake point number emitted")


def _case_calibration(key: SigningKey, settings: AssaySettings) -> None:
    receipt = score(_big_request(), signing_key=key, settings=settings)
    calibration = receipt.payload.calibration
    assert calibration is not None
    assert math.isclose(calibration.ece, 0.2)  # float aggregate: compare with tolerance
    print(f"[5] calibration shipped: ECE={calibration.ece}, Brier={calibration.brier}")


def _case_composite(key: SigningKey) -> None:
    receipt = composite_score(_composite_request(), signing_key=key)
    payload = receipt.payload
    assert payload.score == 0.8  # noqa: PLR2004
    assert payload.interval_low == 0.7  # noqa: PLR2004
    assert payload.interval_high == 0.9  # noqa: PLR2004
    assert verify(receipt, expected_public_key=_pubkey(key)) is True
    print(f"[6] composite: {payload.score} in [{payload.interval_low}, {payload.interval_high}]")


def main() -> int:
    """Run all six acceptance cases; return 0 on success."""
    key = SigningKey(_SEED)
    settings = AssaySettings()
    _case_reproducible(key, settings)
    _case_offline_verify(key, settings)
    _case_tamper(key, settings)
    _case_abstain(key, settings)
    _case_calibration(key, settings)
    _case_composite(key)
    print("all six acceptance cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
