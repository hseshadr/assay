"""Behavioral contract for Assay's immutable scoring models."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from assay import (
    AdditiveRequest,
    AdditiveTerm,
    ClampPolicy,
    Component,
    Direction,
    ExplainedComponent,
    Interval,
    Method,
    MinimumRequest,
    NativeScale,
    Operation,
    ScoreResult,
    WeightedMeanRequest,
)
from assay.errors import InvalidScoreRequest

_INPUTS_HASH = "sha256:7f83b1657ff1fc53b92dc18148a1d65dfa13514d74c69915a0b7543842cff331"


def _scale() -> NativeScale:
    return NativeScale(minimum=0, maximum=15, direction=Direction.HIGHER_IS_BETTER)


def _component(identifier: str = "reliability", weight: float | None = 15) -> Component:
    return Component(
        id=identifier,
        label="Reliability",
        value=13,
        scale=_scale(),
        interval=None,
        weight=weight,
    )


def _term(identifier: str = "semantic") -> AdditiveTerm:
    return AdditiveTerm(
        id=identifier,
        label="Semantic similarity",
        value=0.8,
        coefficient=0.75,
        operation=Operation.ADD,
        interval=None,
    )


def _explained(identifier: str = "reliability") -> ExplainedComponent:
    return ExplainedComponent(
        id=identifier,
        raw=13,
        normalized=13 / 15,
        operation=Operation.ADD,
        coefficient=0.15,
        contribution=0.13,
    )


def test_should_forbid_extra_fields_on_component_boundaries() -> None:
    # Given
    models = (
        _scale(),
        Interval(low=12, high=14),
        _component(),
        _term(),
        _explained(),
        Method(id="weighted_mean", version="northstar-v2"),
    )

    # When / Then
    for model in models:
        payload = model.model_dump()
        payload["extra"] = True
        with pytest.raises(ValidationError):
            type(model).model_validate(payload)


def test_should_forbid_extra_fields_on_request_boundaries() -> None:
    # Given
    requests = (
        WeightedMeanRequest(
            method_version="northstar-v2", components=(_component(),), clamp="reject"
        ),
        AdditiveRequest(method_version="edge-v1", terms=(_term(),), clamp="clamp"),
        MinimumRequest(
            method_version="alma-v1", components=(_component(weight=None),), clamp="reject"
        ),
    )

    # When / Then
    for request in requests:
        payload = request.model_dump()
        payload["extra"] = True
        with pytest.raises(ValidationError):
            type(request).model_validate(payload)


def test_should_freeze_every_contract_model() -> None:
    # Given
    scale = _scale()

    # When / Then
    with pytest.raises(ValidationError):
        scale.minimum = 1


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_scale_numbers(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        NativeScale(minimum=bad, maximum=1, direction=Direction.HIGHER_IS_BETTER)


@pytest.mark.parametrize(("minimum", "maximum"), [(1, 1), (2, 1)])
def test_should_reject_nonincreasing_native_scales(minimum: float, maximum: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_scale"):
        NativeScale(
            minimum=minimum,
            maximum=maximum,
            direction=Direction.HIGHER_IS_BETTER,
        )


def test_should_require_an_explicit_scale_direction() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        NativeScale(minimum=0, maximum=1)


def test_should_support_both_declared_directions() -> None:
    # Given / When
    higher = NativeScale(minimum=0, maximum=1, direction="higher_is_better")
    lower = NativeScale(minimum=0, maximum=1, direction="lower_is_better")

    # Then
    assert higher.direction is Direction.HIGHER_IS_BETTER
    assert lower.direction is Direction.LOWER_IS_BETTER


@pytest.mark.parametrize(("low", "high"), [(2, 1), (1, 1)])
def test_should_reject_unordered_or_zero_width_intervals(low: float, high: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_interval"):
        Interval(low=low, high=high)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_interval_numbers(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        Interval(low=0, high=bad)


@pytest.mark.parametrize("identifier", ["", " space", "two words", "Uppercase", "a/b"])
def test_should_reject_unstable_component_ids(identifier: str) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_identifier"):
        _component(identifier)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_component_values_and_weights(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        Component(id="value", label="Value", value=bad, scale=_scale(), weight=1)
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        Component(id="weight", label="Weight", value=1, scale=_scale(), weight=bad)


@pytest.mark.parametrize("weight", [0, -1])
def test_should_reject_nonpositive_weighted_mean_weights(weight: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_weight"):
        _component(weight=weight)


def test_should_require_nonempty_unique_weighted_components() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.empty_components"):
        WeightedMeanRequest(method_version="northstar-v2", components=(), clamp="reject")
    with pytest.raises(ValidationError, match=r"assay\.duplicate_identifier"):
        WeightedMeanRequest(
            method_version="northstar-v2",
            components=(_component(), _component()),
            clamp="reject",
        )


def test_should_require_a_weight_for_every_weighted_component() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.missing_weight"):
        WeightedMeanRequest(
            method_version="northstar-v2",
            components=(_component(weight=None),),
            clamp="reject",
        )


def test_should_reject_out_of_range_components_without_clamping() -> None:
    # Given
    component = Component(id="reliability", label="Reliability", value=16, scale=_scale(), weight=1)

    # When / Then
    with pytest.raises(ValidationError, match=r"assay\.out_of_range"):
        WeightedMeanRequest(method_version="northstar-v2", components=(component,), clamp="reject")
    assert WeightedMeanRequest(
        method_version="northstar-v2", components=(component,), clamp="clamp"
    )


def test_should_require_an_explicit_clamp_policy_for_every_request() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        WeightedMeanRequest(method_version="northstar-v2", components=(_component(),))
    with pytest.raises(ValidationError):
        AdditiveRequest(method_version="edge-v1", terms=(_term(),))
    with pytest.raises(ValidationError):
        MinimumRequest(method_version="alma-v1", components=(_component(weight=None),))


def test_should_support_both_explicit_clamp_policies() -> None:
    # Given / When
    rejected = WeightedMeanRequest(
        method_version="northstar-v2", components=(_component(),), clamp="reject"
    )
    clamped = WeightedMeanRequest(
        method_version="northstar-v2", components=(_component(),), clamp="clamp"
    )

    # Then
    assert rejected.clamp is ClampPolicy.REJECT
    assert clamped.clamp is ClampPolicy.CLAMP


@pytest.mark.parametrize("coefficient", [-1, -0.1])
def test_should_reject_negative_additive_coefficients(coefficient: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_coefficient"):
        AdditiveTerm(
            id="semantic",
            label="Semantic",
            value=0.8,
            coefficient=coefficient,
            operation=Operation.ADD,
        )


def test_should_require_explicit_additive_operations() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        AdditiveTerm(id="semantic", label="Semantic", value=0.8, coefficient=0.75)


def test_should_support_add_and_subtract_operations() -> None:
    # Given / When
    added = _term()
    subtracted = _term().model_copy(update={"operation": Operation.SUBTRACT})

    # Then
    assert added.operation is Operation.ADD
    assert subtracted.operation is Operation.SUBTRACT


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_additive_numbers(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        AdditiveTerm(id="term", label="Term", value=bad, coefficient=1, operation="add")
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        AdditiveRequest(method_version="edge-v1", terms=(_term(),), intercept=bad, clamp="reject")


def test_should_require_nonempty_unique_additive_terms() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.empty_terms"):
        AdditiveRequest(method_version="edge-v1", terms=(), clamp="reject")
    with pytest.raises(ValidationError, match=r"assay\.duplicate_identifier"):
        AdditiveRequest(method_version="edge-v1", terms=(_term(), _term()), clamp="reject")


def test_should_require_nonempty_unique_minimum_components() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.empty_components"):
        MinimumRequest(method_version="alma-v1", components=(), clamp="reject")
    with pytest.raises(ValidationError, match=r"assay\.duplicate_identifier"):
        MinimumRequest(
            method_version="alma-v1",
            components=(_component(weight=None), _component(weight=None)),
            clamp="reject",
        )


def test_should_reject_out_of_range_minimum_intervals_without_clamping() -> None:
    # Given
    component = Component(
        id="strength",
        label="Strength",
        value=14,
        scale=_scale(),
        interval=Interval(low=14, high=16),
    )

    # When / Then
    with pytest.raises(ValidationError, match=r"assay\.out_of_range"):
        MinimumRequest(method_version="alma-v1", components=(component,), clamp="reject")


def test_should_preserve_declaration_order() -> None:
    # Given
    request = WeightedMeanRequest(
        method_version="northstar-v2",
        components=(_component("zeta"), _component("alpha")),
        clamp="reject",
    )

    # When / Then
    assert tuple(item.id for item in request.components) == ("zeta", "alpha")


def test_should_round_trip_every_request_shape_through_json() -> None:
    # Given
    requests = (
        WeightedMeanRequest(
            method_version="northstar-v2", components=(_component(),), clamp="reject"
        ),
        AdditiveRequest(method_version="edge-v1", terms=(_term(),), intercept=0.1, clamp="clamp"),
        MinimumRequest(
            method_version="alma-v1",
            components=(_component(weight=None),),
            clamp="reject",
        ),
    )

    # When / Then
    for request in requests:
        assert type(request).model_validate_json(request.model_dump_json()) == request


def test_should_round_trip_a_result_with_explicit_deterministic_interval() -> None:
    # Given
    result = ScoreResult(
        method=Method(id="weighted_mean", version="northstar-v2"),
        score=0.88,
        interval=None,
        components=(_explained(),),
        inputs_hash=_INPUTS_HASH,
    )

    # When
    payload = result.model_dump_json()

    # Then
    assert '"interval":null' in payload
    assert ScoreResult.model_validate_json(payload) == result


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_result_and_explanation_numbers(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        ExplainedComponent(
            id="reliability",
            raw=13,
            normalized=13 / 15,
            operation=Operation.ADD,
            coefficient=0.15,
            contribution=bad,
        )
    with pytest.raises(ValidationError, match=r"assay\.invalid_number"):
        ScoreResult(
            method=Method(id="minimum", version="alma-v1"),
            score=bad,
            interval=None,
            components=(_explained(),),
            inputs_hash=_INPUTS_HASH,
        )


def test_should_reject_malformed_result_input_hashes() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match=r"assay\.invalid_inputs_hash"):
        ScoreResult(
            method=Method(id="minimum", version="alma-v1"),
            score=0.5,
            interval=None,
            components=(_explained(),),
            inputs_hash="sha256:not-a-digest",
        )


def test_should_redact_caller_values_from_contract_errors() -> None:
    # Given
    sentinel = "PII-SENTINEL-ALICE"

    # When
    with pytest.raises(ValidationError) as caught:
        Component(id=sentinel, label="Name", value=math.inf, scale=_scale(), weight=1)

    # Then
    assert sentinel not in str(caught.value)
    assert "assay." in str(caught.value)


def test_should_redact_caller_values_from_domain_errors() -> None:
    # Given
    sentinel = "PII-SENTINEL-ALICE"

    # When
    error = InvalidScoreRequest(sentinel)

    # Then
    assert str(error) == "assay.invalid_request"
    assert sentinel not in str(error)
