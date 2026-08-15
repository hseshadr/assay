"""Literals the docs promise, pinned to the literal — not to themselves.

A constant asserted only against its own source is unguarded: ``assert
settings.ranking_k == AssaySettings().ranking_k`` holds at every value, and a test
shaped that way stays green through the exact change it exists to catch. Every
assertion here writes the number the documentation states out loud, so changing the
default without changing the docs fails here.

These sit apart from ``test_settings.py`` on purpose: that file tests the settings
mechanism (defaults exist, env overrides win), this one tests that specific published
promises are still true.
"""

from __future__ import annotations

import json
from pathlib import Path

from assay.settings import AssaySettings

_METRICS = Path("testdata/vectors/metrics.json")

# README, same section: "metrics.json holds 23 hand-computed metric cases: 7 ranking and
# 7 ranking refusals, 5 classification and 4 classification refusals".
_DOCUMENTED_METRIC_CASES = {
    "ranking": 7,
    "ranking_refusals": 7,
    "classification": 5,
    "classification_refusals": 4,
}
_DOCUMENTED_METRIC_TOTAL = 23

# src/assay/ranking.py: "10 is the conventional 'first page' depth".
_DOCUMENTED_RANKING_K = 10


def test_should_match_documented_metric_vector_counts() -> None:
    # Given the shared metric vectors both language suites replay
    metrics = json.loads(_METRICS.read_text(encoding="utf-8"))
    # When each section is counted
    # Then the counts are exactly the ones the README states. The sibling assertions in
    # the two replay suites are `>= 6` and `>= 5` — loose bounds on shape, which stay
    # green while a case quietly goes missing from one language's coverage.
    for section, documented in _DOCUMENTED_METRIC_CASES.items():
        assert len(metrics[section]) == documented, section
    assert sum(len(metrics[s]) for s in _DOCUMENTED_METRIC_CASES) == _DOCUMENTED_METRIC_TOTAL


def test_should_match_documented_default_ranking_cutoff() -> None:
    # Given settings with no ASSAY_* overrides
    settings = AssaySettings()
    # When the ranking cut-off is read
    # Then it is the documented first-page depth, written here as the literal 10 so the
    # default cannot drift away from the sentence that explains it.
    assert settings.ranking_k == _DOCUMENTED_RANKING_K
