"""Assay: the scoring engine that refuses to lie — the score face of the Avow envelope.

The scoring surface needs the heavy scientific stack (scikit-learn / scipy / numpy),
installed via the ``avow[assay]`` extra. If it is missing we fail with a coded
``ScoringExtraMissing`` instead of a raw ``ModuleNotFoundError`` traceback."""

from __future__ import annotations

from assay.errors import ScoringExtraMissing
from avow import __version__

try:
    from assay.api import agreement_score, composite_score, ranking_score, replay, score, verify
except ModuleNotFoundError as exc:  # pragma: no cover - only without the [assay] extra
    raise ScoringExtraMissing("install avow[assay] to use the scoring face") from exc

__all__ = [
    "__version__",
    "agreement_score",
    "composite_score",
    "ranking_score",
    "replay",
    "score",
    "verify",
]
