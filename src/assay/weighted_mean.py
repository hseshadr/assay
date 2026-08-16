"""Normalized positive weighted-mean composition."""

from __future__ import annotations

from assay.composite import finite_output, inputs_hash, interval_or_none, left_add
from assay.contracts import (
    Component,
    ExplainedComponent,
    Interval,
    Method,
    Operation,
    ScoreResult,
    WeightedMeanRequest,
)
from assay.normalize import normalize


def _weight(component: Component) -> float:
    if component.weight is None:  # pragma: no cover - the request contract rejects this
        raise AssertionError("validated weighted component has no weight")
    return component.weight


def _total_weight(request: WeightedMeanRequest) -> float:
    return left_add(_weight(component) for component in request.components)


def _explain(
    component: Component, spec: WeightedMeanRequest, coefficient: float
) -> ExplainedComponent:
    normalized = normalize(component.value, component.scale, spec.clamp)
    contribution = finite_output(normalized * coefficient)
    return ExplainedComponent(
        id=component.id,
        raw=component.value,
        normalized=normalized,
        declared_weight=_weight(component),
        operation=Operation.ADD,
        coefficient=coefficient,
        contribution=contribution,
        contribution_interval=_contribution_interval(component, spec, coefficient),
    )


def _normalized_bounds(component: Component, request: WeightedMeanRequest) -> tuple[float, float]:
    interval = component.interval
    if interval is None:
        point = normalize(component.value, component.scale, request.clamp)
        return point, point
    first = normalize(interval.low, component.scale, request.clamp)
    second = normalize(interval.high, component.scale, request.clamp)
    return min(first, second), max(first, second)


def _contribution_interval(
    component: Component, request: WeightedMeanRequest, coefficient: float
) -> Interval | None:
    if component.interval is None:
        return None
    low, high = _normalized_bounds(component, request)
    return interval_or_none(finite_output(low * coefficient), finite_output(high * coefficient))


def _coefficients(request: WeightedMeanRequest, total: float) -> tuple[float, ...]:
    return tuple(finite_output(_weight(component) / total) for component in request.components)


def _weighted_bound(rows: tuple[ExplainedComponent, ...], *, high: bool) -> float:
    index = 1 if high else 0
    bounds = (
        row.contribution
        if row.contribution_interval is None
        else (row.contribution_interval.low, row.contribution_interval.high)[index]
        for row in rows
    )
    return left_add(bounds)


def _result_interval(rows: tuple[ExplainedComponent, ...]) -> Interval | None:
    if not any(row.contribution_interval is not None for row in rows):
        return None
    low = _weighted_bound(rows, high=False)
    high = _weighted_bound(rows, high=True)
    return interval_or_none(low, high)


def _rows(request: WeightedMeanRequest, total: float) -> tuple[ExplainedComponent, ...]:
    coefficients = _coefficients(request, total)
    return tuple(
        _explain(component, request, coefficient)
        for component, coefficient in zip(request.components, coefficients, strict=True)
    )


def weighted_mean(request: WeightedMeanRequest) -> ScoreResult:
    """Compose a validated normalized weighted mean in declared input order."""
    validated = WeightedMeanRequest.model_validate(request)
    total = _total_weight(validated)
    rows = _rows(validated, total)
    return ScoreResult(
        method=Method(id=validated.method, version=validated.method_version),
        score=left_add(row.contribution for row in rows),
        interval=_result_interval(rows),
        clamp=validated.clamp,
        intercept=None,
        weight_total=total,
        components=rows,
        inputs_hash=inputs_hash(validated),
    )
