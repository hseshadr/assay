"""Transitional release guard: publication remains disabled until Task 9."""

from __future__ import annotations

import sys

_DISABLED_MESSAGE = "publication disabled until Task 9 release hardening"


def main() -> int:
    """Reject every publication attempt until release hardening is implemented."""
    print(_DISABLED_MESSAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
