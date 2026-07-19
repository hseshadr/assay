"""The signed receipt: schema + Ed25519 sign/verify.

The signed content (``ReceiptPayload``) is a pure function of the scoring inputs —
no timestamps — so identical inputs yield an identical payload, an identical
content-hash, and (Ed25519 being deterministic) an identical signature. Verification
recomputes the hash (catching tampered content) and checks the detached signature
(catching a forged or mismatched key).

Unification note (design, not built here): ``sign_payload`` / ``verify_signature`` /
``payload_digest`` form a payload-agnostic **trust envelope** — they operate only on
the canonical JSON of a frozen subject model. ``ReceiptPayload`` is the *score* face's
subject. A future *effect* face ("Writ") would define its own frozen subject model and
reuse this exact hash-sign-verify seam unchanged; only the subject differs, never the
envelope. Do not add the effect face here."""

from __future__ import annotations

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey
from pydantic import BaseModel, ConfigDict

from assay.canonical import canonical_bytes, content_hash
from assay.errors import ReplayMismatch, SignatureInvalid


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


class ReceiptPayload(BaseModel):
    """The deterministic, signable content of a receipt (no wall-clock time).

    This is the *subject* the score face fills; the envelope below signs it without
    knowing what it carries, so a future effect-face subject can reuse the envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assay_version: str
    metric: str
    metric_version: str
    inputs_hash: str
    score: float | None
    interval_low: float | None = None
    interval_high: float | None = None
    abstained: bool = False
    classification: ClassificationDetail | None = None
    calibration: CalibrationDetail | None = None
    composite: CompositeDetail | None = None


class ScoreReceipt(BaseModel):
    """A payload plus its content-hash, public key and Ed25519 signature."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: ReceiptPayload
    payload_hash: str
    public_key: str
    signature: str


def payload_digest(payload: ReceiptPayload) -> str:
    """Content-hash of the canonical payload."""
    return content_hash(payload.model_dump(mode="json"))


def sign_payload(payload: ReceiptPayload, signing_key: SigningKey) -> ScoreReceipt:
    """Hash and Ed25519-sign a payload into a verifiable receipt."""
    message = canonical_bytes(payload.model_dump(mode="json"))
    signature = signing_key.sign(message).signature
    return ScoreReceipt(
        payload=payload,
        payload_hash=payload_digest(payload),
        public_key=bytes(signing_key.verify_key).hex(),
        signature=signature.hex(),
    )


def _check_hash(receipt: ScoreReceipt) -> None:
    if payload_digest(receipt.payload) != receipt.payload_hash:
        raise ReplayMismatch("payload hash does not match payload content")


def verify_signature(receipt: ScoreReceipt, *, expected_public_key: str) -> None:
    """Verify a receipt against a **pinned** signer key.

    Authenticity requires knowing *whose* signature to trust. The receipt's own
    ``public_key`` field lives outside the signed payload, so a re-signed forgery
    can swap in the attacker's key and pass a bare signature check. We therefore
    reject — independent of the signature — any receipt whose embedded key is not
    the ``expected_public_key`` the caller pinned out-of-band, then recompute the
    hash and verify the detached Ed25519 signature under that pinned key."""
    _check_hash(receipt)
    if receipt.public_key != expected_public_key:
        raise SignatureInvalid("receipt public key is not the expected signer")
    message = canonical_bytes(receipt.payload.model_dump(mode="json"))
    # Malformed / wrong-length hex (bytes.fromhex, VerifyKey) raises ValueError; a
    # bad signature raises BadSignatureError. Both are verification failures, so we
    # fail closed with a coded SignatureInvalid rather than leaking a raw traceback.
    try:
        verify_key = VerifyKey(bytes.fromhex(expected_public_key))
        verify_key.verify(message, bytes.fromhex(receipt.signature))
    except (ValueError, BadSignatureError) as exc:
        raise SignatureInvalid("signature does not match payload") from exc
