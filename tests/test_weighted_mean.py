"""Behavioral contract for normalized weighted-mean composition."""

from __future__ import annotations

import math

from assay import (
    ClampPolicy,
    Component,
    Direction,
    Interval,
    NativeScale,
    Operation,
    WeightedMeanRequest,
    compose,
)
from assay.composite import inputs_preimage


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
