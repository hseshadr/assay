"""Shared deterministic composition helpers and the legacy composite adapter."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final, NoReturn

from assay.contracts import (
    AdditiveRequest,
    AdditiveTerm,
    Component,
    Interval,
    MinimumRequest,
    ScoreRequest,
    WeightedMeanRequest,
)
from assay.errors import ContractCode, ContractValidationError, InvalidScoreRequest

MIN_SUBSCORES: Final = 3
_PREIMAGE_VERSION: Final = "assay.request/v1"


def _fail(code: ContractCode) -> NoReturn:
    raise ContractValidationError(code) from None


def canonical_zero(value: float) -> float:
    """Return portable positive zero without changing any other finite value."""
    return 0.0 if value == 0.0 else value


def finite_output(value: float) -> float:
    """Refuse non-finite arithmetic before it reaches a result contract."""
    if not math.isfinite(value):
        _fail(ContractCode.INVALID_NUMBER)
    return canonical_zero(value)


def left_add(values: Iterable[float], initial: float = 0.0) -> float:
    """Add in declared order using direct IEEE-754 operations."""
    total = finite_output(initial)
    for value in values:
        total = finite_output(total + value)
    return total


def interval_or_none(low: float, high: float) -> Interval | None:
    """Represent a collapsed propagated interval as deterministic output."""
    ordered_low = finite_output(min(low, high))
    ordered_high = finite_output(max(low, high))
    return None if ordered_low == ordered_high else Interval(low=ordered_low, high=ordered_high)


def _float_token(value: float) -> str:
    return f"f64:{struct.pack('!d', value).hex()}"


def _interval_token(interval: Interval | None) -> object:
    if interval is None:
        return None
    return (_float_token(interval.low), _float_token(interval.high))


def _component_token(component: Component) -> object:
    scale = component.scale
    weight = None if component.weight is None else _float_token(component.weight)
    return (
        component.id,
        component.label,
        _float_token(component.value),
        (_float_token(scale.minimum), _float_token(scale.maximum), scale.direction.value),
        _interval_token(component.interval),
        weight,
    )


def _term_token(term: AdditiveTerm) -> object:
    return (
        term.id,
        term.label,
        _float_token(term.value),
        _float_token(term.coefficient),
        term.operation.value,
        _interval_token(term.interval),
    )


def _weighted_token(request: WeightedMeanRequest) -> object:
    components = tuple(_component_token(item) for item in request.components)
    return (
        _PREIMAGE_VERSION,
        request.method,
        request.method_version,
        request.clamp.value,
        components,
    )


def _additive_token(request: AdditiveRequest) -> object:
    policy = None if request.clamp is None else request.clamp.value
    terms = tuple(_term_token(item) for item in request.terms)
    return (
        _PREIMAGE_VERSION,
        request.method,
        request.method_version,
        policy,
        _float_token(request.intercept),
        terms,
    )


def _minimum_token(request: MinimumRequest) -> object:
    components = tuple(_component_token(item) for item in request.components)
    return (
        _PREIMAGE_VERSION,
        request.method,
        request.method_version,
        request.clamp.value,
        components,
    )


def inputs_preimage(request: ScoreRequest) -> str:
    """Encode a request as UTF-8 JSON arrays with every float as big-endian f64 hex."""
    if isinstance(request, WeightedMeanRequest):
        token = _weighted_token(request)
    elif isinstance(request, AdditiveRequest):
        token = _additive_token(request)
    else:
        token = _minimum_token(request)
    return json.dumps(token, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def inputs_hash(request: ScoreRequest) -> str:
    """Hash the documented, order-preserving, cross-language request preimage."""
    digest = hashlib.sha256(inputs_preimage(request).encode()).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class SubScore:
    """Legacy v0 input retained until the optional-metrics migration."""

    name: str
    value: float
    low: float
    high: float
    scale_min: float
    scale_max: float
    weight: float


@dataclass(frozen=True)
class NormalizedSubScore:
    """Legacy normalized part retained for source compatibility."""

    name: str
    normalized_value: float
    weight: float


@dataclass(frozen=True)
class CompositeScore:
    """Legacy v0 result retained for source compatibility."""

    value: float
    low: float
    high: float
    parts: tuple[NormalizedSubScore, ...]


def _require_legacy_count(subscores: Sequence[SubScore]) -> None:
    if len(subscores) < MIN_SUBSCORES:
        raise InvalidScoreRequest


def _require_legacy_scales(subscores: Sequence[SubScore]) -> None:
    if any(score.scale_max <= score.scale_min for score in subscores):
        raise InvalidScoreRequest


def _require_legacy_weights(subscores: Sequence[SubScore]) -> None:
    if any(score.weight <= 0 for score in subscores):
        raise InvalidScoreRequest


def _require_legacy_intervals(subscores: Sequence[SubScore]) -> None:
    if any(not score.low <= score.value <= score.high for score in subscores):
        raise InvalidScoreRequest


def _validate_legacy(subscores: Sequence[SubScore]) -> None:
    _require_legacy_count(subscores)
    _require_legacy_scales(subscores)
    _require_legacy_weights(subscores)
    _require_legacy_intervals(subscores)


def _legacy_normalize(value: float, score: SubScore) -> float:
    result = (value - score.scale_min) / (score.scale_max - score.scale_min)
    return min(1.0, max(0.0, result))


def _legacy_weighted(
    subscores: Sequence[SubScore], total: float, pick: Callable[[SubScore], float]
) -> float:
    return sum(score.weight * _legacy_normalize(pick(score), score) for score in subscores) / total


def _legacy_part(score: SubScore) -> NormalizedSubScore:
    return NormalizedSubScore(score.name, _legacy_normalize(score.value, score), score.weight)


def composite(subscores: Sequence[SubScore]) -> CompositeScore:
    """Run the legacy v0 weighted composite while callers migrate to ``compose``."""
    _validate_legacy(subscores)
    total = sum(score.weight for score in subscores)
    return CompositeScore(
        value=_legacy_weighted(subscores, total, lambda score: score.value),
        low=_legacy_weighted(subscores, total, lambda score: score.low),
        high=_legacy_weighted(subscores, total, lambda score: score.high),
        parts=tuple(_legacy_part(score) for score in subscores),
    )
