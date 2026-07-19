"""Assay: the scoring engine that refuses to lie."""

from __future__ import annotations

from assay._version import __version__
from assay.api import composite_score, replay, score, verify

__all__ = ["__version__", "composite_score", "replay", "score", "verify"]
