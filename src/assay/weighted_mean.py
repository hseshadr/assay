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


def _explain(component: Component, spec: WeightedMeanRequest, total: float) -> ExplainedComponent:
    normalized = normalize(component.value, component.scale, spec.clamp)
    coefficient = finite_output(_weight(component) / total)
    contribution = finite_output(normalized * coefficient)
    return ExplainedComponent(
        id=component.id,
        raw=component.value,
        normalized=normalized,
        operation=Operation.ADD,
        coefficient=coefficient,
        contribution=contribution,
    )


def _normalized_bounds(component: Component, request: WeightedMeanRequest) -> tuple[float, float]:
    interval = component.interval
    if interval is None:
        point = normalize(component.value, component.scale, request.clamp)
        return point, point
    first = normalize(interval.low, component.scale, request.clamp)
    second = normalize(interval.high, component.scale, request.clamp)
    return min(first, second), max(first, second)


def _weighted_bound(request: WeightedMeanRequest, total: float, *, high: bool) -> float:
    contributions = []
    for component in request.components:
        bounds = _normalized_bounds(component, request)
        normalized = bounds[1] if high else bounds[0]
        contributions.append(finite_output(normalized * _weight(component) / total))
    return left_add(contributions)


def _result_interval(request: WeightedMeanRequest, total: float) -> Interval | None:
    if not any(component.interval is not None for component in request.components):
        return None
    low = _weighted_bound(request, total, high=False)
    high = _weighted_bound(request, total, high=True)
    return interval_or_none(low, high)


def weighted_mean(request: WeightedMeanRequest) -> ScoreResult:
    """Compose a validated normalized weighted mean in declared input order."""
    validated = WeightedMeanRequest.model_validate(request)
    total = _total_weight(validated)
    rows = tuple(_explain(component, validated, total) for component in validated.components)
    return ScoreResult(
        method=Method(id=validated.method, version=validated.method_version),
        score=left_add(row.contribution for row in rows),
        interval=_result_interval(validated, total),
        components=rows,
        inputs_hash=inputs_hash(validated),
        selected_component_id=None,
    )
