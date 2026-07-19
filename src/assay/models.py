"""Typed request models at the input boundary. Frozen and ``extra="forbid"`` so a
malformed or ambiguous request is rejected before any computation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ScoreRequest(BaseModel):
    """A classification scoring request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    metric_version: str
    y_true: tuple[int, ...]
    y_score: tuple[float, ...]
    threshold: float = 0.5


class SubScoreInput(BaseModel):
    """One sub-score with its native scale and interval, for a composite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: float
    low: float
    high: float
    scale_min: float
    scale_max: float
    weight: float


class CompositeRequest(BaseModel):
    """A weighted multi-scale composite request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = "weighted_composite"
    metric_version: str
    subscores: tuple[SubScoreInput, ...]
