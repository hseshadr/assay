"""Verify that an npm channel points at the target or a newer same-channel release."""

from __future__ import annotations

import sys

from scripts.registry_release_guard import dist_tag_is_current_or_newer

_ARGUMENT_COUNT = 3


def main() -> int:
    if len(sys.argv) != _ARGUMENT_COUNT:
        print("usage: verify_npm_dist_tag.py TARGET CURRENT", file=sys.stderr)
        return 1
    try:
        valid = dist_tag_is_current_or_newer(sys.argv[1], sys.argv[2])
    except ValueError:
        valid = False
    if not valid:
        print("npm dist-tag is missing, older, or on another channel", file=sys.stderr)
        return 1
    print("verified npm dist-tag is exact or newer on the same channel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
