"""Behavioral contract for limiting-component composition."""

from __future__ import annotations

from assay import (
    ClampPolicy,
    Component,
    Direction,
    Interval,
    MinimumRequest,
    NativeScale,
    Operation,
    compose,
)


def _component(
    identifier: str,
    value: float,
    *,
    interval: Interval | None = None,
    direction: Direction = Direction.HIGHER_IS_BETTER,
) -> Component:
    return Component(
        id=identifier,
        label=identifier.replace("_", " ").title(),
        value=value,
        scale=NativeScale(minimum=0.0, maximum=100.0, direction=direction),
        interval=interval,
    )


def _request(*components: Component) -> MinimumRequest:
    return MinimumRequest(
        method="minimum",
        method_version="almamesh.domain-strength-v1",
        components=components,
        clamp=ClampPolicy.REJECT,
    )


def test_should_select_lowest_normalized_component_and_explain_every_candidate() -> None:
    # Given two valid axes where the second normalized value is lower
    request = _request(_component("shadbala_pct", 80.0), _component("sav_pct", 55.0))
    # When the limiting score is composed
    result = compose(request)
    # Then the result names the limiter without hiding the other candidate
    assert result.score == 0.55
    assert result.selected_component_id == "sav_pct"
    assert tuple(row.id for row in result.components) == ("shadbala_pct", "sav_pct")
    assert tuple(row.raw for row in result.components) == (80.0, 55.0)
    assert tuple(row.normalized for row in result.components) == (0.8, 0.55)
    assert tuple(row.coefficient for row in result.components) == (1.0, 1.0)
    assert tuple(row.contribution for row in result.components) == (0.8, 0.55)
    assert all(row.operation is Operation.ADD for row in result.components)


def test_should_choose_first_tied_component_without_sorting_identifiers() -> None:
    # Given equal axes whose lexical order is opposite their declaration order
    forward = _request(_component("shadbala_pct", 60.0), _component("sav_pct", 60.0))
    reverse = _request(_component("sav_pct", 60.0), _component("shadbala_pct", 60.0))
    # When each declaration is composed
    forward_result = compose(forward)
    reverse_result = compose(reverse)
    # Then first occurrence—not lexical ID order—selects the limiting explanation
    assert forward_result.score == reverse_result.score == 0.6
    assert forward_result.selected_component_id == "shadbala_pct"
    assert reverse_result.selected_component_id == "sav_pct"


def test_should_accept_one_component_without_legacy_minimum_three_rule() -> None:
    # Given one mathematically valid limiting component
    request = _request(_component("only_axis", 40.0))
    # When it is composed
    result = compose(request)
    # Then the single normalized candidate is both score and selected component
    assert result.score == 0.4
    assert result.selected_component_id == "only_axis"


def test_should_propagate_minimum_of_normalized_low_and_high_bounds() -> None:
    # Given interval axes including a lower-is-better native direction
    request = _request(
        _component("quality", 60.0, interval=Interval(low=50.0, high=80.0)),
        _component(
            "latency",
            30.0,
            interval=Interval(low=10.0, high=40.0),
            direction=Direction.LOWER_IS_BETTER,
        ),
    )
    # When endpoint minima are propagated independently
    result = compose(request)
    # Then direction is encoded before taking each minimum
    assert result.score == 0.6
    assert result.interval == Interval(low=0.5, high=0.8)
    assert result.selected_component_id == "quality"


def test_should_serialize_explicit_selected_component_without_application_band() -> None:
    # Given a minimum result with one limiting axis
    result = compose(_request(_component("limiter", 25.0), _component("other", 75.0)))
    # When its portable result is serialized
    payload = result.model_dump(mode="json")
    # Then selection is explicit and no application-owned band is invented
    assert payload["selected_component_id"] == "limiter"
    assert "band" not in payload
