"""Weighted multi-scale composite with propagated uncertainty.

Each sub-score is normalized to [0,1] by its own scale, then combined as a
positive-weighted mean. Because the mean is monotone in each input, the composite
interval is the same weighted mean applied to the sub-scores' lows and highs —
exact interval arithmetic, no fabricated tightening."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from assay.errors import InvalidScoreRequest

MIN_SUBSCORES: Final[int] = 3


@dataclass(frozen=True)
class SubScore:
    """One input sub-score with its native scale and an uncertainty interval."""

    name: str
    value: float
    low: float
    high: float
    scale_min: float
    scale_max: float
    weight: float


@dataclass(frozen=True)
class NormalizedSubScore:
    """A sub-score after normalization to [0,1]."""

    name: str
    normalized_value: float
    weight: float


@dataclass(frozen=True)
class CompositeScore:
    """The composite value with its propagated interval and normalized parts."""

    value: float
    low: float
    high: float
    parts: tuple[NormalizedSubScore, ...]


def _require_min_count(subscores: Sequence[SubScore]) -> None:
    if len(subscores) < MIN_SUBSCORES:
        raise InvalidScoreRequest("composite needs at least three sub-scores")


def _require_increasing_scales(subscores: Sequence[SubScore]) -> None:
    if any(s.scale_max <= s.scale_min for s in subscores):
        raise InvalidScoreRequest("scale_max must exceed scale_min")


def _require_positive_weight(subscores: Sequence[SubScore]) -> None:
    if any(s.weight <= 0 for s in subscores):
        raise InvalidScoreRequest("each sub-score weight must be positive")


def _validate(subscores: Sequence[SubScore]) -> None:
    _require_min_count(subscores)
    _require_increasing_scales(subscores)
    _require_positive_weight(subscores)


def _normalize(x: float, s: SubScore) -> float:
    return min(1.0, max(0.0, (x - s.scale_min) / (s.scale_max - s.scale_min)))


def _weighted(
    subscores: Sequence[SubScore], total_w: float, pick: Callable[[SubScore], float]
) -> float:
    return sum(s.weight * _normalize(pick(s), s) for s in subscores) / total_w


def _part(s: SubScore) -> NormalizedSubScore:
    return NormalizedSubScore(s.name, _normalize(s.value, s), s.weight)


def composite(subscores: Sequence[SubScore]) -> CompositeScore:
    """Combine >= 3 multi-scale sub-scores into one interval-carrying composite."""
    _validate(subscores)
    total_w = sum(s.weight for s in subscores)
    return CompositeScore(
        value=_weighted(subscores, total_w, lambda s: s.value),
        low=_weighted(subscores, total_w, lambda s: s.low),
        high=_weighted(subscores, total_w, lambda s: s.high),
        parts=tuple(_part(s) for s in subscores),
    )
