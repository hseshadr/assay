"""First-occurrence minimum composition over normalized components."""

from __future__ import annotations

from assay.composite import inputs_hash, interval_or_none
from assay.contracts import (
    Component,
    ExplainedComponent,
    Interval,
    Method,
    MinimumRequest,
    Operation,
    ScoreResult,
)
from assay.normalize import normalize


def _normalized(component: Component, request: MinimumRequest, value: float) -> float:
    return normalize(value, component.scale, request.clamp)


def _explain(component: Component, request: MinimumRequest) -> ExplainedComponent:
    candidate = _normalized(component, request, component.value)
    return ExplainedComponent(
        id=component.id,
        raw=component.value,
        normalized=candidate,
        operation=Operation.ADD,
        coefficient=1.0,
        contribution=candidate,
    )


def _bounds(component: Component, request: MinimumRequest) -> tuple[float, float]:
    interval = component.interval
    if interval is None:
        point = _normalized(component, request, component.value)
        return point, point
    first = _normalized(component, request, interval.low)
    second = _normalized(component, request, interval.high)
    return min(first, second), max(first, second)


def _propagated_bounds(request: MinimumRequest) -> tuple[float, float]:
    bounds = tuple(_bounds(component, request) for component in request.components)
    return min(low for low, _ in bounds), min(high for _, high in bounds)


def _result_interval(request: MinimumRequest) -> Interval | None:
    if not any(component.interval is not None for component in request.components):
        return None
    return interval_or_none(*_propagated_bounds(request))


def minimum(request: MinimumRequest) -> ScoreResult:
    """Return the first lowest normalized candidate and identify it explicitly."""
    validated = MinimumRequest.model_validate(request)
    rows = tuple(_explain(component, validated) for component in validated.components)
    selected = min(rows, key=lambda row: row.contribution)
    return ScoreResult(
        method=Method(id=validated.method, version=validated.method_version),
        score=selected.contribution,
        interval=_result_interval(validated),
        components=rows,
        inputs_hash=inputs_hash(validated),
        selected_component_id=selected.id,
    )
