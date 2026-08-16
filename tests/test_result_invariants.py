"""Method-specific invariants for independently replayable score results."""

from __future__ import annotations

import json

import pytest

from assay import (
    ClampPolicy,
    ContractValidationError,
    ExplainedComponent,
    Interval,
    Method,
    Operation,
    ScoreResult,
)
from assay.errors import ContractCode

_HASH = "sha256:7f83b1657ff1fc53b92dc18148a1d65dfa13514d74c69915a0b7543842cff331"


def _row(
    identifier: str,
    normalized: float | None,
    coefficient: float,
    contribution: float,
    *,
    operation: Operation = Operation.ADD,
    interval: Interval | None = None,
    declared_weight: float | None = None,
) -> ExplainedComponent:
    raw = contribution / coefficient if coefficient else 0.0
    return ExplainedComponent(
        id=identifier,
        raw=raw,
        normalized=normalized,
        declared_weight=declared_weight,
        operation=operation,
        coefficient=coefficient,
        contribution=contribution,
        contribution_interval=interval,
    )


def _weighted() -> ScoreResult:
    return ScoreResult(
        method=Method(id="weighted_mean", version="review-v1"),
        score=1.0,
        interval=None,
        clamp=ClampPolicy.REJECT,
        intercept=None,
        weight_total=1.0,
        components=(_row("quality", 1.0, 1.0, 1.0, declared_weight=1.0),),
        inputs_hash=_HASH,
        selected_component_id=None,
    )


def _additive(
    *, score: float = 0.30000000000000004, clamp: ClampPolicy | None = None
) -> ScoreResult:
    return ScoreResult(
        method=Method(id="additive", version="review-v1"),
        score=score,
        interval=None,
        clamp=clamp,
        intercept=0.1,
        weight_total=None,
        components=(_row("signal", None, 0.5, 0.2),),
        inputs_hash=_HASH,
        selected_component_id=None,
    )


def _minimum() -> ScoreResult:
    return ScoreResult(
        method=Method(id="minimum", version="review-v1"),
        score=0.4,
        interval=None,
        clamp=ClampPolicy.REJECT,
        intercept=None,
        weight_total=None,
        components=(_row("first", 0.6, 1.0, 0.6), _row("second", 0.4, 1.0, 0.4)),
        inputs_hash=_HASH,
        selected_component_id="second",
    )


def _assert_invalid(payload: dict[str, object]) -> None:
    with pytest.raises(ContractValidationError) as caught:
        ScoreResult.model_validate(payload)
    assert caught.value.code == ContractCode.INVALID_RESULT.value
    assert str(caught.value) == "assay.invalid_result"


@pytest.mark.parametrize("result", [_weighted(), _additive()])
def test_should_forbid_selection_on_nonminimum_results(result: ScoreResult) -> None:
    # Given a valid weighted or additive result
    payload = result.model_dump()
    # When it falsely claims one selected component
    payload["selected_component_id"] = "quality"
    # Then the method-specific result contract rejects it without caller data
    _assert_invalid(payload)


@pytest.mark.parametrize("selected", [None, "first", "missing"])
def test_should_require_minimum_to_select_first_declared_lowest_row(
    selected: str | None,
) -> None:
    # Given a minimum result with its second row as the unique minimum
    payload = _minimum().model_dump()
    # When selection is absent, nonminimal, or missing from the explanations
    payload["selected_component_id"] = selected
    # Then it cannot cross the public result boundary
    _assert_invalid(payload)


@pytest.mark.parametrize(
    ("factory", "field", "value"),
    [
        (_weighted, "normalized", None),
        (_weighted, "operation", "subtract"),
        (_weighted, "coefficient", 0.0),
        (_weighted, "contribution", 0.4),
        (_additive, "normalized", 0.4),
        (_additive, "contribution", 0.4),
        (_minimum, "operation", "subtract"),
        (_minimum, "coefficient", 0.5),
        (_minimum, "contribution", 0.5),
    ],
)
def test_should_reject_method_inconsistent_explanation_rows(
    factory: object, field: str, value: object
) -> None:
    # Given an otherwise valid method-specific explanation
    assert callable(factory)
    payload = factory().model_dump()
    # When one row violates that method's arithmetic shape
    payload["components"][0][field] = value
    # Then the result is rejected with one stable, value-free code
    _assert_invalid(payload)


def test_should_replay_additive_score_from_intercept_policy_and_signed_rows() -> None:
    # Given an additive result whose stored score replays in declared IEEE-754 order
    payload = _additive().model_dump()
    # When its score is changed without changing the replay inputs
    payload["score"] = 0.4
    # Then the inconsistent score is rejected
    _assert_invalid(payload)


def test_should_replay_final_additive_clamp_from_result_policy() -> None:
    # Given an unbounded additive result above one
    result = ScoreResult(
        method=Method(id="additive", version="review-v1"),
        score=1.2,
        interval=None,
        clamp=None,
        intercept=1.0,
        weight_total=None,
        components=(_row("gain", None, 1.0, 0.2),),
        inputs_hash=_HASH,
        selected_component_id=None,
    )
    payload = result.model_dump()
    # When the wire claims the same score used final clamping
    payload["clamp"] = "clamp"
    # Then the clamp policy cannot disagree with the replayed score
    _assert_invalid(payload)


@pytest.mark.parametrize("factory", [_weighted, _additive, _minimum])
def test_should_require_method_specific_intercept_and_clamp_fields(factory: object) -> None:
    # Given a valid result from one closed composition method
    assert callable(factory)
    payload = factory().model_dump()
    # When the method's intercept/policy shape is swapped
    if payload["method"]["id"] == "additive":
        payload["intercept"] = None
    else:
        payload["intercept"] = 0.0
    # Then the result is not accepted as another method's shape
    _assert_invalid(payload)


def test_should_replay_weighted_interval_from_ordered_contribution_bounds() -> None:
    # Given two weighted rows and their complete contribution intervals
    result = ScoreResult(
        method=Method(id="weighted_mean", version="review-v1"),
        score=0.5,
        interval=Interval(low=0.30000000000000004, high=0.7),
        clamp=ClampPolicy.REJECT,
        intercept=None,
        weight_total=1.0,
        components=(
            _row(
                "first",
                0.4,
                0.5,
                0.2,
                interval=Interval(low=0.1, high=0.3),
                declared_weight=0.5,
            ),
            _row(
                "second",
                0.6,
                0.5,
                0.3,
                interval=Interval(low=0.2, high=0.4),
                declared_weight=0.5,
            ),
        ),
        inputs_hash=_HASH,
        selected_component_id=None,
    )
    payload = result.model_dump()
    # When one aggregate endpoint no longer matches declared-order replay
    payload["interval"]["low"] = 0.31
    # Then public JSON validation rejects it
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_result"):
        ScoreResult.model_validate_json(json.dumps(payload))


def test_should_reject_forged_one_component_weighted_coefficient() -> None:
    # Given a one-component weighted result whose only effective coefficient must be one
    payload = _weighted().model_dump()
    # When point arithmetic is forged consistently around an impossible coefficient
    payload["components"][0]["coefficient"] = 0.5
    payload["components"][0]["contribution"] = 0.5
    payload["score"] = 0.5
    # Then declared-weight replay rejects it even though its local multiplication agrees
    _assert_invalid(payload)


def test_should_require_weight_total_on_weighted_result_json() -> None:
    # Given a weighted result payload with its replay total removed
    payload = _weighted().model_dump()
    payload.pop("weight_total", None)
    # When it crosses the JSON boundary
    with pytest.raises(ContractValidationError) as caught:
        ScoreResult.model_validate_json(json.dumps(payload))
    # Then the required wire field cannot be inferred
    assert caught.value.code == ContractCode.MISSING_FIELD.value


def test_should_reject_inconsistent_weight_total_on_copy() -> None:
    # Given a valid weighted result with one declared unit of weight
    result = _weighted()
    row = result.components[0].model_copy(update={"coefficient": 0.5, "contribution": 0.5})
    # When a validated copy uses locally consistent arithmetic with a false total
    with pytest.raises(ContractValidationError) as caught:
        result.model_copy(update={"score": 0.5, "weight_total": 2.0, "components": (row,)})
    # Then exact declared-order replay rejects the inconsistency
    assert caught.value.code == ContractCode.INVALID_RESULT.value


@pytest.mark.parametrize("factory", [_additive, _minimum])
def test_should_emit_null_weight_metadata_on_nonweighted_results(factory: object) -> None:
    # Given an additive or minimum result with explicit null weight metadata
    assert callable(factory)
    payload = factory().model_dump()
    # When its portable result shape is inspected
    # Then weighted replay fields are present but explicitly unused
    assert payload["weight_total"] is None
    assert all(row["declared_weight"] is None for row in payload["components"])


@pytest.mark.parametrize("factory", [_additive, _minimum])
def test_should_reject_weight_total_on_nonweighted_results(factory: object) -> None:
    # Given an additive or minimum result
    assert callable(factory)
    payload = factory().model_dump()
    # When its result claims a weighted total
    payload["weight_total"] = 1.0
    # Then the method-specific result invariant rejects that metadata
    _assert_invalid(payload)


@pytest.mark.parametrize("factory", [_additive, _minimum])
def test_should_reject_declared_row_weight_on_nonweighted_results(factory: object) -> None:
    # Given an additive or minimum result
    assert callable(factory)
    payload = factory().model_dump()
    # When one explanation claims a declared weighted-mean weight
    payload["components"][0]["declared_weight"] = 1.0
    # Then the method-specific explanation invariant rejects it
    _assert_invalid(payload)


def test_should_revalidate_result_invariants_on_model_copy() -> None:
    # Given a valid limiting result
    result = _minimum()
    # When a copy attempts to select a nonminimal row
    with pytest.raises(ContractValidationError) as caught:
        result.model_copy(update={"selected_component_id": "first"})
    # Then revalidation uses the same stable public invariant code
    assert caught.value.code == ContractCode.INVALID_RESULT.value
