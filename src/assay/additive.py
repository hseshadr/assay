"""Declared-order additive and subtractive score composition."""

from __future__ import annotations

from typing import NoReturn

from assay.composite import canonical_zero, finite_output, inputs_hash, interval_or_none
from assay.contracts import (
    AdditiveRequest,
    AdditiveTerm,
    ClampPolicy,
    ExplainedComponent,
    Interval,
    Method,
    Operation,
    ScoreResult,
)
from assay.errors import ContractCode, ContractValidationError


def _fail(code: ContractCode) -> NoReturn:
    raise ContractValidationError(code) from None


def _contribution(term: AdditiveTerm, value: float | None = None) -> float:
    raw = term.value if value is None else value
    return finite_output(raw * term.coefficient)


def _apply(total: float, contribution: float, operation: Operation) -> float:
    if operation is Operation.ADD:
        return finite_output(total + contribution)
    return finite_output(total - contribution)


def _final(value: float, policy: ClampPolicy | None) -> float:
    result = finite_output(value)
    if policy is None:
        return result
    if policy is ClampPolicy.CLAMP:
        return canonical_zero(min(1.0, max(0.0, result)))
    if not 0.0 <= result <= 1.0:
        _fail(ContractCode.OUT_OF_RANGE)
    return result


def _explain(term: AdditiveTerm) -> ExplainedComponent:
    return ExplainedComponent(
        id=term.id,
        raw=term.value,
        normalized=None,
        operation=term.operation,
        coefficient=term.coefficient,
        contribution=_contribution(term),
        contribution_interval=interval_or_none(*_term_bounds(term)),
    )


def _point(request: AdditiveRequest, rows: tuple[ExplainedComponent, ...]) -> float:
    total = finite_output(request.intercept)
    for row in rows:
        total = _apply(total, row.contribution, row.operation)
    return _final(total, request.clamp)


def _term_bounds(term: AdditiveTerm) -> tuple[float, float]:
    if term.interval is None:
        contribution = _contribution(term)
        return contribution, contribution
    return _contribution(term, term.interval.low), _contribution(term, term.interval.high)


def _advance_bounds(low: float, high: float, term: AdditiveTerm) -> tuple[float, float]:
    term_low, term_high = _term_bounds(term)
    if term.operation is Operation.ADD:
        return finite_output(low + term_low), finite_output(high + term_high)
    return finite_output(low - term_high), finite_output(high - term_low)


def _result_interval(request: AdditiveRequest) -> Interval | None:
    if not any(term.interval is not None for term in request.terms):
        return None
    low = high = finite_output(request.intercept)
    for term in request.terms:
        low, high = _advance_bounds(low, high, term)
    return interval_or_none(_final(low, request.clamp), _final(high, request.clamp))


def additive(request: AdditiveRequest) -> ScoreResult:
    """Compose an explicit left-to-right sum with an optional final unit bound."""
    validated = AdditiveRequest.model_validate(request)
    rows = tuple(_explain(term) for term in validated.terms)
    return ScoreResult(
        method=Method(id=validated.method, version=validated.method_version),
        score=_point(validated, rows),
        interval=_result_interval(validated),
        clamp=validated.clamp,
        intercept=validated.intercept,
        components=rows,
        inputs_hash=inputs_hash(validated),
        selected_component_id=None,
    )
