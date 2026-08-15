"""Import-safe transitional entry point for the scoring-only distribution."""

from __future__ import annotations

import sys

from assay.errors import ScoringCorePending


def main() -> int:
    """Refuse every command until the scoring contract is implemented."""
    sys.stderr.write(f"FAIL: {ScoringCorePending.code}\n")
    return 1
