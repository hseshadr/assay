"""Offline verifier. Given a receipt and the signer's pinned public key (both held
without any network or original inputs), confirm the receipt's content-hash matches
its payload, its embedded key is the expected signer, and its Ed25519 signature is
valid under that pinned key."""

from __future__ import annotations

from assay.receipt import ScoreReceipt, verify_signature


def verify_receipt(receipt: ScoreReceipt, *, expected_public_key: str) -> None:
    """Verify a receipt offline against a pinned signer; raises a typed error on
    any failure (bad hash, wrong signer, or invalid signature)."""
    verify_signature(receipt, expected_public_key=expected_public_key)
