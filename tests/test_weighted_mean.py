"""Behavioral contract for normalized weighted-mean composition."""

from __future__ import annotations

import math

from assay import (
    ClampPolicy,
    Component,
    Direction,
    Interval,
    MinimumRequest,
    NativeScale,
    Operation,
    WeightedMeanRequest,
    compose,
)
from assay.composite import inputs_hash, inputs_preimage


def _scale(
    minimum: float,
    maximum: float,
    direction: Direction = Direction.HIGHER_IS_BETTER,
) -> NativeScale:
    return NativeScale(minimum=minimum, maximum=maximum, direction=direction)


def _request(*components: Component) -> WeightedMeanRequest:
    return WeightedMeanRequest(
        method="weighted_mean",
        method_version="northstar-v2",
        components=components,
        clamp=ClampPolicy.REJECT,
    )


def test_should_normalize_before_dividing_by_total_weight() -> None:
    # Given differently scaled components in a declared non-lexical order
    request = _request(
        Component(
            id="z_reliability",
            label="Reliability",
            value=13.0,
            scale=_scale(0.0, 15.0),
            weight=15.0,
        ),
        Component(
            id="a_latency",
            label="Latency",
            value=80.0,
            scale=_scale(0.0, 100.0, Direction.LOWER_IS_BETTER),
            weight=5.0,
        ),
    )
    # When the weighted mean is composed
    result = compose(request)
    # Then normalization precedes weighting and explanations preserve declared order
    assert result.score == 0.7000000000000001
    assert tuple(row.id for row in result.components) == ("z_reliability", "a_latency")
    assert tuple(row.raw for row in result.components) == (13.0, 80.0)
    assert tuple(row.normalized for row in result.components) == (13.0 / 15.0, 0.2)
    assert tuple(row.declared_weight for row in result.components) == (15.0, 5.0)
    assert result.weight_total == 20.0
    assert tuple(row.coefficient for row in result.components) == (0.75, 0.25)
    assert tuple(row.contribution for row in result.components) == (0.65, 0.05)
    assert all(row.operation is Operation.ADD for row in result.components)


def test_should_propagate_weighted_interval_endpoints_in_declared_direction() -> None:
    # Given higher- and lower-is-better inputs with uncertainty intervals
    request = _request(
        Component(
            id="quality",
            label="Quality",
            value=80.0,
            interval=Interval(low=70.0, high=90.0),
            scale=_scale(0.0, 100.0),
            weight=3.0,
        ),
        Component(
            id="latency",
            label="Latency",
            value=20.0,
            interval=Interval(low=10.0, high=40.0),
            scale=_scale(0.0, 100.0, Direction.LOWER_IS_BETTER),
            weight=1.0,
        ),
    )
    # When endpoints are propagated through the same positive weights
    result = compose(request)
    # Then raw interval order is reversed only by lower-is-better normalization
    assert result.interval == Interval(low=0.6749999999999999, high=0.9)
    assert result.score == 0.8


def test_should_reuse_effective_coefficient_for_point_and_interval_endpoints() -> None:
    # Given a value whose weight-first endpoint arithmetic rounds above its point
    request = _request(
        Component(
            id="fraction",
            label="Fraction",
            value=0.1,
            interval=Interval(low=0.1, high=0.2),
            scale=_scale(0.0, 1.0),
            weight=3.0,
        )
    )
    # When the point and interval use one precomputed effective coefficient
    result = compose(request)
    # Then the point lies inside the exact replayable contribution interval
    assert result.score == 0.1
    assert result.interval == Interval(low=0.1, high=0.2)
    assert result.components[0].coefficient == 1.0
    assert result.components[0].contribution_interval == result.interval


def test_should_emit_method_schema_determinism_and_pinned_inputs_hash() -> None:
    # Given one deterministic literal request with a cross-language preimage
    request = _request(
        Component(
            id="reliability",
            label="Reliability",
            value=13.0,
            scale=_scale(0.0, 15.0),
            weight=15.0,
        )
    )
    # When it is composed
    result = compose(request)
    # Then identity and the independently pinned request digest are exact
    assert result.schema_version == "assay.result/v1"
    assert result.method.id == "weighted_mean"
    assert result.method.version == "northstar-v2"
    assert result.interval is None
    assert result.selected_component_id is None
    assert inputs_preimage(request) == (
        '["assay.request/v1","weighted_mean","northstar-v2","reject",'
        '[["reliability","Reliability","f64:402a000000000000",'
        '["f64:0000000000000000","f64:402e000000000000","higher_is_better"],'
        'null,"f64:402e000000000000"]]]'
    )
    assert result.inputs_hash == (
        "sha256:760833068215d7e1e4c48823466019fe9a9e0a6fef324d01021546aa64f87bb1"
    )


def test_should_return_canonical_positive_zero() -> None:
    # Given a component whose normalized result is signed zero
    request = _request(
        Component(
            id="zero",
            label="Zero",
            value=-0.0,
            scale=_scale(0.0, 1.0),
            weight=1.0,
        )
    )
    # When it is composed
    result = compose(request)
    # Then every observable zero is canonical positive zero
    assert result.score == 0.0
    assert math.copysign(1.0, result.score) == 1.0
    assert math.copysign(1.0, result.components[0].normalized or 0.0) == 1.0
    assert math.copysign(1.0, result.components[0].contribution) == 1.0


def test_should_compose_when_a_positive_effective_weight_underflows_to_zero() -> None:
    # Given valid positive weights whose binary64 ratio is not representable
    request = _request(
        Component(id="tiny", label="Tiny", value=1.0, scale=_scale(0.0, 1.0), weight=5e-324),
        Component(id="large", label="Large", value=0.5, scale=_scale(0.0, 1.0), weight=1e308),
    )
    # When the weighted score is composed and crosses JSON/copy boundaries
    result = compose(request)
    wire = result.model_dump_json()
    replayed = type(result).model_validate_json(wire)
    copied = replayed.model_copy()
    # Then declared weights remain positive while the public effective zero is canonical
    assert copied.weight_total == 1e308
    assert tuple(row.declared_weight for row in copied.components) == (5e-324, 1e308)
    assert tuple(row.coefficient for row in copied.components) == (0.0, 1.0)
    assert math.copysign(1.0, copied.components[0].coefficient) == 1.0
    assert copied.score == 0.5
    assert "-0.0" not in wire


def test_should_hash_every_weighted_request_field_class() -> None:
    # Given one baseline and variants changing each request field class independently
    component = Component(
        id="quality",
        label="Quality",
        value=0.25,
        scale=_scale(0.0, 1.0),
        interval=None,
        weight=1.0,
    )
    baseline = _request(component)
    scale_variants = (
        component.model_copy(update={"scale": _scale(-1.0, 1.0)}),
        component.model_copy(update={"scale": _scale(0.0, 2.0)}),
        component.model_copy(update={"scale": _scale(0.0, 1.0, Direction.LOWER_IS_BETTER)}),
    )
    component_variants = (
        component.model_copy(update={"id": "other"}),
        component.model_copy(update={"label": "Other"}),
        component.model_copy(update={"value": 0.5}),
        component.model_copy(update={"interval": Interval(low=0.1, high=0.3)}),
        component.model_copy(update={"weight": 2.0}),
        *scale_variants,
    )
    variants = (
        MinimumRequest(
            method="minimum",
            method_version="northstar-v2",
            components=(component,),
            clamp=ClampPolicy.REJECT,
        ),
        baseline.model_copy(update={"method_version": "northstar-v3"}),
        baseline.model_copy(update={"clamp": ClampPolicy.CLAMP}),
        *(baseline.model_copy(update={"components": (item,)}) for item in component_variants),
        baseline.model_copy(
            update={"components": (component, component.model_copy(update={"id": "second"}))}
        ),
        baseline.model_copy(
            update={"components": (component.model_copy(update={"id": "second"}), component)}
        ),
    )
    # When each complete request is hashed
    hashes = {inputs_hash(baseline), *(inputs_hash(request) for request in variants)}
    # Then method/version/policy/order and every component/scale field affect the digest
    assert len(hashes) == len(variants) + 1
