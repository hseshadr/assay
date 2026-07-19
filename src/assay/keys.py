"""Ed25519 signing-key custody. The private key is a 32-byte seed written to a
0600 file; it is never logged and never committed (``*.key`` is gitignored). The
public verify key is recovered from the seed and travels inside each receipt."""

from __future__ import annotations

import os
from pathlib import Path

from nacl.signing import SigningKey

_SEED_BYTES = 32
_OWNER_ONLY = 0o600


def generate_signing_key() -> SigningKey:
    """Generate a fresh random Ed25519 signing key."""
    return SigningKey.generate()


def save_signing_key(key: SigningKey, *, path: Path) -> None:
    """Write the 32-byte seed to ``path`` with owner-only permissions."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _OWNER_ONLY)
    with os.fdopen(fd, "wb") as handle:
        handle.write(bytes(key))


def load_signing_key(path: Path) -> SigningKey:
    """Load a signing key from its 32-byte seed file."""
    seed = path.read_bytes()
    if len(seed) != _SEED_BYTES:
        raise ValueError(f"signing key must be {_SEED_BYTES} bytes, got {len(seed)}")
    return SigningKey(seed)
