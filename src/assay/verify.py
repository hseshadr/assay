"""Offline verifier. Given only a receipt (no network, no original inputs), confirm
its content-hash matches its payload and its Ed25519 signature is valid."""

from __future__ import annotations

from assay.receipt import ScoreReceipt, verify_signature


def verify_receipt(receipt: ScoreReceipt) -> None:
    """Verify a receipt offline; raises a typed error on any failure."""
    verify_signature(receipt)
