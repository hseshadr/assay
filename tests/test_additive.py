"""Behavioral contract for ordered additive composition."""

from __future__ import annotations

import math

import pytest

from assay import (
    AdditiveRequest,
    AdditiveTerm,
    ClampPolicy,
    Interval,
    Operation,
    compose,
)
from assay.composite import inputs_hash
from assay.errors import ContractCode, ContractValidationError


def _term(
    identifier: str,
    value: float,
    coefficient: float,
    operation: Operation = Operation.ADD,
    interval: Interval | None = None,
) -> AdditiveTerm:
    return AdditiveTerm(
        id=identifier,
        label=identifier.replace("_", " ").title(),
        value=value,
        coefficient=coefficient,
        operation=operation,
        interval=interval,
    )


def _request(
    *terms: AdditiveTerm,
    intercept: float = 0.0,
    clamp: ClampPolicy | None = None,
) -> AdditiveRequest:
    return AdditiveRequest(
        method="additive",
        method_version="consumer-v1",
        terms=terms,
        intercept=intercept,
        clamp=clamp,
    )


def test_should_preserve_unbounded_negative_consumer_score_when_policy_is_null() -> None:
    # Given EdgeReco's valid negative case with only a repetition penalty
    request = _request(
        _term("popularity", 0.0, 0.4),
        _term("repetition_penalty", 1.0, 0.25, Operation.SUBTRACT),
    )
    # When the explicitly unbounded request is composed
    result = compose(request)
    # Then no hidden clamp or rejection changes the consumer's arithmetic
    assert result.score == -0.25
    assert tuple(row.contribution for row in result.components) == (0.0, 0.25)
    assert tuple(row.operation for row in result.components) == (
        Operation.ADD,
        Operation.SUBTRACT,
    )


def test_should_apply_intercept_and_terms_strictly_left_to_right_without_division() -> None:
    # Given terms whose IEEE-754 result changes when they are reordered or averaged
    request = _request(
        _term("small", 1.0, 1.0),
        _term("large", 1e16, 1.0, Operation.SUBTRACT),
        intercept=1e16,
    )
    # When terms are evaluated in their declared order
    result = compose(request)
    # Then the direct ordered sum is returned and explanations remain unnormalized
    assert result.score == 0.0
    assert tuple(row.id for row in result.components) == ("small", "large")
    assert tuple(row.raw for row in result.components) == (1.0, 1e16)
    assert tuple(row.normalized for row in result.components) == (None, None)
    assert tuple(row.coefficient for row in result.components) == (1.0, 1.0)
    assert tuple(row.contribution for row in result.components) == (1.0, 1e16)


def test_should_propagate_add_and_subtract_interval_endpoints() -> None:
    # Given interval terms with different explicit operations
    request = _request(
        _term("benefit", 0.4, 0.5, interval=Interval(low=0.2, high=0.6)),
        _term(
            "penalty",
            0.2,
            0.5,
            Operation.SUBTRACT,
            interval=Interval(low=0.1, high=0.3),
        ),
        intercept=0.1,
    )
    # When their bounds are propagated in declared order
    result = compose(request)
    # Then subtraction uses high for low and low for high
    assert result.score == pytest.approx(0.2)
    assert result.interval == Interval(low=0.05000000000000002, high=0.35000000000000003)


def test_should_propagate_interval_terms_in_declared_ieee_order() -> None:
    # Given endpoint arithmetic whose low bound changes if terms are reversed
    request = _request(
        _term("small", 1.0, 1.0, interval=Interval(low=1.0, high=2.0)),
        _term(
            "large",
            1e16,
            1.0,
            Operation.SUBTRACT,
            interval=Interval(low=1e16, high=1.0000000000000002e16),
        ),
        intercept=1e16,
    )
    # When contribution endpoints advance strictly left-to-right
    result = compose(request)
    # Then rounding preserves the declared-order low rather than a reordered low
    assert result.interval == Interval(low=-2.0, high=2.0)
    assert result.components[0].contribution_interval == Interval(low=1.0, high=2.0)


def test_should_clamp_only_after_all_terms_and_preserve_explanations() -> None:
    # Given a sum that exceeds one only before a later explicit subtraction
    request = _request(
        _term("gain", 1.0, 0.4),
        _term("penalty", 1.0, 0.5, Operation.SUBTRACT),
        intercept=0.9,
        clamp=ClampPolicy.CLAMP,
    )
    # When the optional final clamp is selected
    result = compose(request)
    # Then the intermediate 1.3 is not clamped before subtraction produces 0.8
    assert result.score == 0.8
    assert tuple(row.contribution for row in result.components) == (0.4, 0.5)


def test_should_reject_out_of_range_final_score_with_stable_code() -> None:
    # Given the same unbounded arithmetic under the explicit reject policy
    request = _request(_term("signal", 1.0, 1.1), clamp=ClampPolicy.REJECT)
    # When the final score exceeds the unit interval
    with pytest.raises(ContractValidationError) as caught:
        compose(request)
    # Then the public failure is stable and value-free
    assert caught.value.code == ContractCode.OUT_OF_RANGE.value
    assert str(caught.value) == "assay.out_of_range"


def test_should_return_canonical_positive_zero_after_subtraction() -> None:
    # Given equal additive and subtractive terms
    request = _request(_term("gain", 1.0, 1.0), _term("cost", 1.0, 1.0, Operation.SUBTRACT))
    # When their exact result is zero
    result = compose(request)
    # Then portable output does not expose signed zero
    assert result.score == 0.0
    assert math.copysign(1.0, result.score) == 1.0
    assert result.selected_component_id is None


def test_should_hash_every_additive_request_field_class() -> None:
    # Given one baseline and variants changing each ordered additive field class
    term = _term("signal", 0.25, 0.5)
    second = _term("second", 0.1, 0.2)
    baseline = _request(term, second)
    term_variants = (
        term.model_copy(update={"id": "other"}),
        term.model_copy(update={"label": "Other"}),
        term.model_copy(update={"value": 0.5}),
        term.model_copy(update={"coefficient": 0.75}),
        term.model_copy(update={"operation": Operation.SUBTRACT}),
        term.model_copy(update={"interval": Interval(low=0.1, high=0.3)}),
    )
    variants = (
        baseline.model_copy(update={"method_version": "consumer-v2"}),
        baseline.model_copy(update={"clamp": ClampPolicy.REJECT}),
        baseline.model_copy(update={"intercept": 0.1}),
        *(baseline.model_copy(update={"terms": (item, second)}) for item in term_variants),
        baseline.model_copy(update={"terms": (second, term)}),
    )
    # When each complete request is hashed
    hashes = {inputs_hash(baseline), *(inputs_hash(request) for request in variants)}
    # Then version/policy/intercept/order and every term field affect the digest
    assert len(hashes) == len(variants) + 1
