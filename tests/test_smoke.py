"""Smoke test: the package imports and exposes a semantic version.

This is the green-baseline anchor. Real behavior arrives via the TDD plan in
``docs/superpowers/plans/2026-07-19-assay-v0.md``.
"""

from __future__ import annotations

import assay


def test_should_expose_semver_version_when_imported() -> None:
    # Given the installed assay package
    # When reading its version string
    version = assay.__version__
    # Then it is a non-empty three-part semantic version
    parts = version.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
