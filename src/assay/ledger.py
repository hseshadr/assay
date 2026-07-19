"""Append-only, content-addressed receipt ledger (JSONL).

Each line is one ``ScoreReceipt``; its identity is the ``payload_hash``. Appending
never rewrites history. ``verify_integrity`` re-derives each payload's hash and
fails closed if a stored hash disagrees — so on-disk tampering is detectable
without the signing key."""

from __future__ import annotations

from pathlib import Path

from assay.errors import LedgerIntegrityError
from assay.receipt import ScoreReceipt, payload_digest


def append(receipt: ScoreReceipt, *, path: Path) -> None:
    """Append one receipt as a JSON line."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(receipt.model_dump_json() + "\n")


def read_all(path: Path) -> tuple[ScoreReceipt, ...]:
    """Read every receipt from the ledger (empty if the file is absent)."""
    if not path.exists():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(ScoreReceipt.model_validate_json(line) for line in lines if line.strip())


def verify_integrity(path: Path) -> tuple[ScoreReceipt, ...]:
    """Return all receipts, raising if any stored hash disagrees with its content."""
    receipts = read_all(path)
    for receipt in receipts:
        if payload_digest(receipt.payload) != receipt.payload_hash:
            raise LedgerIntegrityError(f"tampered ledger entry: {receipt.payload_hash}")
    return receipts
