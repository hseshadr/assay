"""Standalone replay checks for the portable result wire format."""

from __future__ import annotations

import json

from assay import (
    AdditiveRequest,
    AdditiveTerm,
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


def _term(
    identifier: str,
    value: float,
    operation: Operation,
    interval: Interval,
) -> AdditiveTerm:
    return AdditiveTerm(
        id=identifier,
        label=identifier.title(),
        value=value,
        coefficient=1.0,
        operation=operation,
        interval=interval,
    )


def _signed(total: float, row: dict[str, object], key: str) -> float:
    value = row[key]
    assert isinstance(value, (int, float))
    return total + value if row["operation"] == "add" else total - value


def _replay_additive(payload: dict[str, object]) -> tuple[float, tuple[float, float]]:
    intercept = payload["intercept"]
    rows = payload["components"]
    assert isinstance(intercept, (int, float))
    assert isinstance(rows, list)
    point = low = high = float(intercept)
    for candidate in rows:
        assert isinstance(candidate, dict)
        point = _signed(point, candidate, "contribution")
        interval = candidate["contribution_interval"]
        assert isinstance(interval, dict)
        keys = ("low", "high") if candidate["operation"] == "add" else ("high", "low")
        low = _signed(low, {**candidate, **interval}, keys[0])
        high = _signed(high, {**candidate, **interval}, keys[1])
    assert payload["clamp"] == "clamp"
    return min(1.0, max(0.0, point)), (min(1.0, max(0.0, low)), min(1.0, max(0.0, high)))


def _component(identifier: str, value: float, interval: Interval) -> Component:
    return Component(
        id=identifier,
        label=identifier.title(),
        value=value,
        scale=NativeScale(minimum=0.0, maximum=1.0, direction=Direction.HIGHER_IS_BETTER),
        interval=interval,
        weight=1.0,
    )


def _replay_rows(payload: dict[str, object]) -> tuple[float, tuple[float, float]]:
    rows = payload["components"]
    assert isinstance(rows, list)
    point = low = high = 0.0
    for row in rows:
        assert isinstance(row, dict)
        contribution = row["contribution"]
        interval = row["contribution_interval"]
        assert isinstance(contribution, (int, float))
        assert isinstance(interval, dict)
        point += contribution
        low += interval["low"]
        high += interval["high"]
    return point, (low, high)


def _replay_weighted_rows(payload: dict[str, object]) -> tuple[float, tuple[float, float]]:
    total = payload["weight_total"]
    rows = payload["components"]
    assert isinstance(total, (int, float))
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        weight = row["declared_weight"]
        assert isinstance(weight, (int, float))
        assert row["coefficient"] == weight / total
    return _replay_rows(payload)


def test_should_replay_additive_point_and_interval_from_result_wire_alone() -> None:
    # Given an additive result whose ordered terms carry uncertainty
    request = AdditiveRequest(
        method="additive",
        method_version="standalone-replay-v1",
        terms=(
            _term("benefit", 0.5, Operation.ADD, Interval(low=0.4, high=0.6)),
            _term("penalty", 0.1, Operation.SUBTRACT, Interval(low=0.05, high=0.15)),
        ),
        clamp=ClampPolicy.CLAMP,
        intercept=0.2,
    )
    payload = json.loads(compose(request).model_dump_json())
    assert isinstance(payload, dict)
    # When an independent reader uses only the serialized result
    point, interval = _replay_additive(payload)
    # Then it reproduces the declared point and interval exactly
    assert point == payload["score"] == 0.6
    result_interval = payload["interval"]
    assert isinstance(result_interval, dict)
    assert interval == (result_interval["low"], result_interval["high"])
    assert interval == (0.45000000000000007, 0.75)


def test_should_replay_weighted_point_and_interval_from_result_wire_alone() -> None:
    # Given a weighted result with two uncertain normalized contributions
    request = WeightedMeanRequest(
        method="weighted_mean",
        method_version="standalone-replay-v1",
        components=(
            _component("quality", 0.5, Interval(low=0.4, high=0.6)),
            _component("reliability", 0.25, Interval(low=0.1, high=0.3)),
        ),
        clamp=ClampPolicy.REJECT,
    )
    payload = json.loads(compose(request).model_dump_json())
    assert isinstance(payload, dict)
    # When an independent reader adds only the result's ordered contribution rows
    point, interval = _replay_weighted_rows(payload)
    # Then it reproduces the result without native scales, weights, or the request
    assert payload["clamp"] == "reject"
    assert payload["intercept"] is None
    assert payload["weight_total"] == 2.0
    assert [row["declared_weight"] for row in payload["components"]] == [1.0, 1.0]
    assert point == payload["score"] == 0.375
    assert interval == (payload["interval"]["low"], payload["interval"]["high"])
    assert interval == (0.25, 0.44999999999999996)


def test_should_replay_minimum_selection_and_interval_from_result_wire_alone() -> None:
    # Given a minimum result whose point limiter differs from one low-bound limiter
    components = (
        _component("first", 0.6, Interval(low=0.5, high=0.8)).model_copy(update={"weight": None}),
        _component("second", 0.7, Interval(low=0.4, high=0.9)).model_copy(update={"weight": None}),
    )
    request = MinimumRequest(
        method="minimum",
        method_version="standalone-replay-v1",
        components=components,
        clamp=ClampPolicy.REJECT,
    )
    payload = json.loads(compose(request).model_dump_json())
    assert isinstance(payload, dict)
    rows = payload["components"]
    assert isinstance(rows, list)
    # When an independent reader selects and bounds only the normalized candidates
    selected = min(rows, key=lambda row: row["contribution"])
    lows = [row["contribution_interval"]["low"] for row in rows]
    highs = [row["contribution_interval"]["high"] for row in rows]
    # Then the first point minimum and both endpoint minima reproduce exactly
    assert selected["id"] == payload["selected_component_id"] == "first"
    assert selected["contribution"] == payload["score"] == 0.6
    assert (min(lows), min(highs)) == (payload["interval"]["low"], payload["interval"]["high"])
    assert (min(lows), min(highs)) == (0.4, 0.8)
