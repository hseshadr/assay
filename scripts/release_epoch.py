"""Derive a reproducible Python build epoch from packaged source history."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PACKAGED_PATHS = ("LICENSE", "README.md", "pyproject.toml", "src/assay")
_ROOT_ARGUMENT_COUNT = 2


def source_date_epoch(root: Path) -> int:
    """Return the newest commit time that can affect packaged Python bytes."""
    completed = subprocess.run(  # noqa: S603
        ["git", "log", "-1", "--pretty=%ct", "--", *_PACKAGED_PATHS],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(completed.stdout.strip())


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) == _ROOT_ARGUMENT_COUNT else Path.cwd()
    print(source_date_epoch(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
