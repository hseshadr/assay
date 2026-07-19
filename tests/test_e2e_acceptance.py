from __future__ import annotations

from nacl.signing import SigningKey

from assay.api import score
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
