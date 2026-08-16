"""Behavioral contract for Assay's immutable scoring models."""

from __future__ import annotations

import json
import math
import struct

import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticSerializationError

from assay import (
    AdditiveRequest,
    AdditiveTerm,
    ClampPolicy,
    Component,
    ContractValidationError,
    Direction,
    ExplainedComponent,
    Interval,
    Method,
    MinimumRequest,
    NativeScale,
    Operation,
    ScoreRequest,
    ScoreResult,
    WeightedMeanRequest,
    parse_request,
    parse_request_json,
)
from assay.composite import inputs_preimage
from assay.errors import ContractCode, InvalidScoreRequest

_INPUTS_HASH = "sha256:7f83b1657ff1fc53b92dc18148a1d65dfa13514d74c69915a0b7543842cff331"
_SENTINEL = "PII-SENTINEL-ALICE"


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
        contribution_interval=None,
    )


def _result() -> ScoreResult:
    return ScoreResult(
        method=Method(id="weighted_mean", version="northstar-v2"),
        score=0.13,
        interval=None,
        clamp=ClampPolicy.REJECT,
        intercept=None,
        components=(_explained(),),
        inputs_hash=_INPUTS_HASH,
    )


def _public_models() -> tuple[BaseModel, ...]:
    return (
        _scale(),
        Interval(low=12, high=14),
        _component(),
        _term(),
        _explained(),
        Method(id="weighted_mean", version="northstar-v2"),
        _weighted_request(),
        _additive_request(),
        _minimum_request(),
        _result(),
    )


def _weighted_request() -> WeightedMeanRequest:
    return WeightedMeanRequest(
        method="weighted_mean",
        method_version="northstar-v2",
        components=(_component(),),
        clamp="reject",
    )


def _additive_request() -> AdditiveRequest:
    return AdditiveRequest(
        method="additive",
        method_version="edge-v1",
        terms=(_term(),),
        clamp="clamp",
    )


def test_should_round_trip_explicit_unbounded_additive_policy() -> None:
    # Given an additive request that explicitly declines a final unit bound
    request = AdditiveRequest(
        method="additive",
        method_version="edge-v1",
        terms=(_term(),),
        clamp=None,
    )
    # When it crosses both JSON parsers
    payload = request.model_dump_json()
    # Then null remains explicit and both public paths preserve it
    assert '"clamp":null' in payload
    assert AdditiveRequest.model_validate_json(payload) == request
    assert parse_request_json(payload) == request


def test_should_reject_missing_additive_policy_even_though_null_is_valid() -> None:
    # Given an additive request object with no final-policy field
    payload = _additive_request().model_dump(exclude={"clamp"})
    # When it crosses the public parser
    with pytest.raises(ContractValidationError) as caught:
        parse_request(payload)
    # Then omission is distinct from an explicit unbounded null
    assert caught.value.code == ContractCode.MISSING_FIELD.value


def _minimum_request() -> MinimumRequest:
    return MinimumRequest(
        method="minimum",
        method_version="alma-v1",
        components=(_component(weight=None),),
        clamp="reject",
    )


def test_should_forbid_and_redact_extra_fields_on_every_public_model() -> None:
    # Given / When / Then
    for model in _public_models():
        payload = model.model_dump()
        payload[_SENTINEL] = "private-value"
        with pytest.raises(ContractValidationError) as caught:
            type(model).model_validate(payload)
        assert "assay.unknown_field" in str(caught.value)
        assert _SENTINEL not in str(caught.value)
        assert "private-value" not in str(caught.value)


def test_should_freeze_every_public_model() -> None:
    # Given / When / Then
    for model in _public_models():
        field_name = next(iter(type(model).model_fields))
        with pytest.raises(PydanticValidationError):
            setattr(model, field_name, None)


def _assert_redacted(error: Exception, code: str) -> None:
    text = str(error)
    assert code in text
    assert _SENTINEL not in text
    assert "private-value" not in text


def _assert_code_only(error: ContractValidationError, code: str) -> None:
    assert error.code == code
    assert str(error) == code
    assert error.args == (code,)
    assert error.__context__ is None
    assert error.__cause__ is None
    assert not hasattr(error, "errors")
    assert not hasattr(error, "json")
    assert not hasattr(error, "model_dump")


def test_should_redact_nested_unknown_field_from_direct_construction() -> None:
    # Given
    scale = {"minimum": 0, "maximum": 1, "direction": "higher_is_better"}
    scale[_SENTINEL] = "private-value"

    # When
    with pytest.raises(ContractValidationError) as caught:
        Component(id="quality", label="Quality", value=0.5, scale=scale, weight=1)

    # Then
    _assert_redacted(caught.value, "assay.unknown_field")


def test_should_redact_nested_unknown_field_from_model_validate() -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload["components"][0]["scale"][_SENTINEL] = "private-value"

    # When
    with pytest.raises(ContractValidationError) as caught:
        WeightedMeanRequest.model_validate(payload)

    # Then
    _assert_redacted(caught.value, "assay.unknown_field")


def test_should_redact_nested_unknown_field_from_model_validate_json() -> None:
    # Given
    payload = _additive_request().model_dump()
    payload["terms"][0][_SENTINEL] = "private-value"

    # When
    with pytest.raises(ContractValidationError) as caught:
        AdditiveRequest.model_validate_json(json.dumps(payload))

    # Then
    _assert_redacted(caught.value, "assay.unknown_field")


def test_should_redact_nested_missing_operation_from_model_validate_json() -> None:
    # Given
    payload = _additive_request().model_dump()
    payload["terms"][0]["label"] = _SENTINEL
    payload["terms"][0].pop("operation")

    # When
    with pytest.raises(ContractValidationError) as caught:
        AdditiveRequest.model_validate_json(json.dumps(payload))

    # Then
    _assert_redacted(caught.value, "assay.missing_field")


def test_should_redact_nested_missing_direction_from_model_validate() -> None:
    # Given
    payload = _component().model_dump()
    payload["label"] = _SENTINEL
    payload["scale"].pop("direction")

    # When
    with pytest.raises(ContractValidationError) as caught:
        Component.model_validate(payload)

    # Then
    _assert_redacted(caught.value, "assay.missing_field")


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (NativeScale, {"minimum": _SENTINEL, "maximum": 1}),
        (
            WeightedMeanRequest,
            {
                "method": "weighted_mean",
                "method_version": _SENTINEL,
                "components": (),
            },
        ),
        (
            AdditiveTerm,
            {"id": "term", "label": _SENTINEL, "value": 1, "coefficient": 1},
        ),
    ],
)
def test_should_use_stable_code_for_missing_required_fields(
    model: type[BaseModel], payload: object
) -> None:
    # Given / When
    with pytest.raises(ContractValidationError) as caught:
        model.model_validate(payload)

    # Then
    _assert_redacted(caught.value, "assay.missing_field")


def test_should_require_a_literal_method_on_every_request() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_method"):
        WeightedMeanRequest.model_validate(
            {"method_version": "v1", "components": (), "clamp": "reject"}
        )
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_method"):
        AdditiveRequest.model_validate({"method_version": "v1", "terms": (), "clamp": "reject"})
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_method"):
        MinimumRequest.model_validate({"method_version": "v1", "components": (), "clamp": "reject"})


def test_should_reject_weighted_payload_as_minimum() -> None:
    # Given
    payload = _weighted_request().model_dump()

    # When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_method"):
        MinimumRequest.model_validate(payload)


def test_should_dispatch_and_round_trip_every_request_method() -> None:
    # Given
    requests: tuple[ScoreRequest, ...] = (
        _weighted_request(),
        _additive_request(),
        _minimum_request(),
    )

    # When / Then
    for request in requests:
        parsed = parse_request_json(request.model_dump_json())
        assert type(parsed) is type(request)
        assert parsed == request


@pytest.mark.parametrize("method", [None, _SENTINEL])
def test_should_redact_unknown_or_missing_method_from_parser(method: str | None) -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload["method"] = method

    # When
    with pytest.raises(ContractValidationError) as caught:
        parse_request(payload)

    # Then
    assert str(caught.value) == "assay.invalid_method"
    assert _SENTINEL not in str(caught.value)


def test_should_redact_unknown_method_from_json_parser() -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload["method"] = _SENTINEL

    # When
    with pytest.raises(ContractValidationError) as caught:
        parse_request_json(json.dumps(payload))

    # Then
    assert str(caught.value) == "assay.invalid_method"
    assert _SENTINEL not in str(caught.value)


def test_should_redact_nested_validation_from_exported_parser() -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload["components"][0][_SENTINEL] = "private-value"

    # When
    with pytest.raises(ContractValidationError) as caught:
        parse_request(payload)

    # Then
    assert str(caught.value) == "assay.unknown_field"
    assert _SENTINEL not in str(caught.value)
    assert "private-value" not in str(caught.value)


@pytest.mark.parametrize("value", [[], {}, None, 1, True, "unknown"])
def test_should_reject_nonstring_or_unknown_discriminator_values(value: object) -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload["method"] = value

    # When
    with pytest.raises(ContractValidationError) as caught:
        parse_request(payload)

    # Then
    _assert_code_only(caught.value, "assay.invalid_method")


@pytest.mark.parametrize("payload", [[], {}, None, 1, True, "unknown"])
def test_should_reject_payloads_without_string_discriminator(payload: object) -> None:
    # Given / When
    with pytest.raises(ContractValidationError) as caught:
        parse_request_json(json.dumps(payload))

    # Then
    _assert_code_only(caught.value, "assay.invalid_method")


def test_should_redact_oversized_integer_json_for_every_public_model() -> None:
    # Given
    payload = "9" * 5_000

    # When / Then
    for model in _public_models():
        with pytest.raises(ContractValidationError) as caught:
            type(model).model_validate_json(payload)
        _assert_code_only(caught.value, "assay.invalid_contract")
        assert payload not in repr(caught.value)


def test_should_redact_oversized_integer_json_from_request_parser() -> None:
    # Given
    payload = "9" * 5_000

    # When
    with pytest.raises(ContractValidationError) as caught:
        parse_request_json(payload)

    # Then
    _assert_code_only(caught.value, "assay.invalid_contract")
    assert payload not in repr(caught.value)


def test_should_hide_pydantic_surface_from_direct_constructor_error() -> None:
    # Given
    scale = {"minimum": 0, "maximum": 1, "direction": "higher_is_better"}
    scale[_SENTINEL] = "private-value"

    # When
    with pytest.raises(ContractValidationError) as caught:
        Component(id="quality", label=_SENTINEL, value=0.5, scale=scale)

    # Then
    _assert_code_only(caught.value, "assay.unknown_field")
    _assert_redacted(caught.value, "assay.unknown_field")


def test_should_hide_pydantic_surface_from_model_validate_error() -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload["components"] = _SENTINEL

    # When
    with pytest.raises(ContractValidationError) as caught:
        WeightedMeanRequest.model_validate(payload)

    # Then
    _assert_code_only(caught.value, "assay.invalid_contract")
    assert _SENTINEL not in repr(caught.value)


def test_should_hide_pydantic_surface_from_model_validate_json_error() -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload["components"] = _SENTINEL

    # When
    with pytest.raises(ContractValidationError) as caught:
        WeightedMeanRequest.model_validate_json(json.dumps(payload))

    # Then
    _assert_code_only(caught.value, "assay.invalid_contract")
    assert _SENTINEL not in repr(caught.value)


def test_should_redact_missing_method_from_parser() -> None:
    # Given
    payload = _weighted_request().model_dump()
    payload.pop("method")
    payload["method_version"] = _SENTINEL

    # When
    with pytest.raises(ContractValidationError) as caught:
        parse_request(payload)

    # Then
    assert str(caught.value) == "assay.invalid_method"
    assert _SENTINEL not in str(caught.value)


@pytest.mark.parametrize("loader", [Component.model_validate, Component.model_validate_json])
def test_should_reject_unpaired_unicode_surrogates(loader: object) -> None:
    # Given
    payload = {
        "id": "quality",
        "label": "\ud800",
        "value": 0.5,
        "scale": _scale().model_dump(),
    }
    value = json.dumps(payload) if loader == Component.model_validate_json else payload

    # When
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_text"):
        loader(value)


def test_should_reject_unpaired_unicode_surrogate_from_constructor() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_text"):
        Component(id="quality", label="\ud800", value=0.5, scale=_scale())


def test_should_round_trip_valid_unicode_labels() -> None:
    # Given
    component = Component(id="quality", label="Fiabilité 🌟", value=0.5, scale=_scale())

    # When
    restored = Component.model_validate_json(component.model_dump_json())

    # Then
    assert restored == component


def test_should_revalidate_model_copy_updates() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        _scale().model_copy(update={"minimum": math.nan})
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        _component().model_copy(update={"value": math.inf})
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_method"):
        _weighted_request().model_copy(update={"method": "minimum"})


def test_should_revalidate_forged_nested_scale_instances() -> None:
    # Given
    forged = NativeScale.model_construct(minimum=2, maximum=1, direction=Direction.HIGHER_IS_BETTER)

    # When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_scale"):
        Component(id="quality", label="Quality", value=1, scale=forged)


def test_should_revalidate_forged_components_entering_requests() -> None:
    # Given
    forged = Component.model_construct(
        id="quality", label="Quality", value=math.nan, scale=_scale(), weight=1
    )
    payload = _weighted_request().model_dump()
    payload["components"] = (forged,)

    # When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        WeightedMeanRequest.model_validate(payload)
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        parse_request(payload)


def test_should_revalidate_forged_explanations_entering_results() -> None:
    # Given
    forged = ExplainedComponent.model_construct(
        id="quality",
        raw=1,
        normalized=1,
        operation="add",
        coefficient=1,
        contribution=math.inf,
        contribution_interval=None,
    )
    payload = _result().model_dump()
    payload["components"] = (forged,)

    # When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        ScoreResult.model_validate(payload)


def test_should_refuse_to_serialize_forged_nonfinite_values_as_null() -> None:
    # Given
    forged = NativeScale.model_construct(
        minimum=math.nan, maximum=1, direction=Direction.HIGHER_IS_BETTER
    )

    # When / Then
    with pytest.raises(PydanticSerializationError, match=r"assay\.invalid_number"):
        forged.model_dump_json()


def test_should_reject_alias_and_field_name_duplicates_before_extras() -> None:
    # Given
    payload = _result().model_dump()
    payload["schema_version"] = "assay.result/v1"
    payload[_SENTINEL] = "private-value"

    # When
    with pytest.raises(ContractValidationError) as caught:
        ScoreResult.model_validate(payload)

    # Then
    _assert_code_only(caught.value, "assay.duplicate_field")
    _assert_redacted(caught.value, "assay.duplicate_field")


def test_should_reject_conflicting_alias_validation_paths() -> None:
    # Given
    payload = _result().model_dump()

    # When
    with pytest.raises(ContractValidationError) as caught:
        ScoreResult.model_validate(payload, by_alias=False, by_name=False)

    # Then
    _assert_code_only(caught.value, "assay.invalid_alias_config")


def test_should_accept_documented_score_result_schema_alias_by_default() -> None:
    # Given
    result = _result()
    payload = result.model_dump()

    # When
    restored = ScoreResult.model_validate(payload)

    # Then
    assert payload["schema"] == "assay.result/v1"
    assert restored == result


@pytest.mark.parametrize(
    ("field_name", "by_alias", "by_name"),
    [
        ("schema_version", True, False),
        ("schema", False, True),
    ],
)
def test_should_reject_disabled_score_result_field_spelling(
    field_name: str, by_alias: bool, by_name: bool
) -> None:
    # Given
    payload = _result().model_dump(exclude={"schema_version"})
    payload[field_name] = "assay.result/v1"

    # When
    with pytest.raises(ContractValidationError) as caught:
        ScoreResult.model_validate(payload, by_alias=by_alias, by_name=by_name)

    # Then
    _assert_code_only(caught.value, "assay.unknown_field")


@pytest.mark.parametrize(
    ("by_alias", "by_name"),
    [
        (True, False),
        (False, True),
    ],
)
def test_should_reject_alias_duplicates_before_explicit_spelling_mode(
    by_alias: bool, by_name: bool
) -> None:
    # Given
    payload = _result().model_dump()
    payload["schema_version"] = "assay.result/v1"

    # When
    with pytest.raises(ContractValidationError) as caught:
        ScoreResult.model_validate(payload, by_alias=by_alias, by_name=by_name)

    # Then
    _assert_code_only(caught.value, "assay.duplicate_field")


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_scale_numbers(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        NativeScale(minimum=bad, maximum=1, direction=Direction.HIGHER_IS_BETTER)


@pytest.mark.parametrize(("minimum", "maximum"), [(1, 1), (2, 1)])
def test_should_reject_nonincreasing_native_scales(minimum: float, maximum: float) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_scale"):
        NativeScale(
            minimum=minimum,
            maximum=maximum,
            direction=Direction.HIGHER_IS_BETTER,
        )


def test_should_require_an_explicit_scale_direction() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError):
        NativeScale(minimum=0, maximum=1)


def test_should_support_both_declared_directions() -> None:
    # Given / When
    higher = NativeScale(minimum=0, maximum=1, direction="higher_is_better")
    lower = NativeScale(minimum=0, maximum=1, direction="lower_is_better")

    # Then
    assert higher.direction is Direction.HIGHER_IS_BETTER
    assert lower.direction is Direction.LOWER_IS_BETTER


def test_should_canonicalize_a_forged_valid_direction_member() -> None:
    # Given a StrEnum-shaped Direction that is not a declared member
    forged = str.__new__(Direction, "lower_is_better")
    # When it crosses the NativeScale boundary
    scale = NativeScale(minimum=0, maximum=1, direction=forged)
    # Then the model stores only the exact canonical enum member
    assert scale.direction is Direction.LOWER_IS_BETTER


def test_should_reject_a_forged_unknown_direction_member() -> None:
    # Given a forged Direction carrying an undeclared value
    forged = str.__new__(Direction, "sideways")
    # When it crosses the NativeScale boundary
    with pytest.raises(ContractValidationError) as caught:
        NativeScale(minimum=0, maximum=1, direction=forged)
    # Then validation fails through the stable public code
    assert caught.value.code == ContractCode.INVALID_DIRECTION.value


@pytest.mark.parametrize(("low", "high"), [(2, 1), (1, 1)])
def test_should_reject_unordered_or_zero_width_intervals(low: float, high: float) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_interval"):
        Interval(low=low, high=high)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_interval_numbers(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        Interval(low=0, high=bad)


@pytest.mark.parametrize("identifier", ["", " space", "two words", "Uppercase", "a/b"])
def test_should_reject_unstable_component_ids(identifier: str) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_identifier"):
        _component(identifier)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_reject_nonfinite_component_values_and_weights(bad: float) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        Component(id="value", label="Value", value=bad, scale=_scale(), weight=1)
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        Component(id="weight", label="Weight", value=1, scale=_scale(), weight=bad)


def test_should_canonicalize_all_contract_zeros_before_json_and_request_hashing() -> None:
    # Given signed-zero values across every numeric additive boundary class
    interval = Interval(low=-0.0, high=1.0)
    term = AdditiveTerm(
        id="zero",
        label="Zero",
        value=-0.0,
        coefficient=-0.0,
        operation=Operation.ADD,
        interval=interval,
    )
    request = AdditiveRequest(
        method="additive",
        method_version="zero-v1",
        terms=(term,),
        clamp=None,
        intercept=-0.0,
    )
    # When the models serialize and enter the cross-language hash preimage
    serialized = request.model_dump_json()
    preimage = inputs_preimage(request)
    # Then no public number or IEEE-754 token retains a negative-zero sign bit
    assert "-0.0" not in serialized
    assert "f64:8000000000000000" not in preimage
    assert struct.pack("!d", request.intercept).hex() == "0000000000000000"
    assert struct.pack("!d", request.terms[0].value).hex() == "0000000000000000"
    assert struct.pack("!d", request.terms[0].coefficient).hex() == "0000000000000000"
    assert struct.pack("!d", request.terms[0].interval.low).hex() == "0000000000000000"


@pytest.mark.parametrize("weight", [0, -1])
def test_should_reject_nonpositive_weighted_mean_weights(weight: float) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_weight"):
        _component(weight=weight)


def test_should_require_nonempty_unique_weighted_components() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.empty_components"):
        WeightedMeanRequest(
            method="weighted_mean", method_version="northstar-v2", components=(), clamp="reject"
        )
    with pytest.raises(ContractValidationError, match=r"assay\.duplicate_identifier"):
        WeightedMeanRequest(
            method="weighted_mean",
            method_version="northstar-v2",
            components=(_component(), _component()),
            clamp="reject",
        )


def test_should_require_a_weight_for_every_weighted_component() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.missing_weight"):
        WeightedMeanRequest(
            method="weighted_mean",
            method_version="northstar-v2",
            components=(_component(weight=None),),
            clamp="reject",
        )


def test_should_reject_out_of_range_components_without_clamping() -> None:
    # Given
    component = Component(id="reliability", label="Reliability", value=16, scale=_scale(), weight=1)

    # When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.out_of_range"):
        WeightedMeanRequest(
            method="weighted_mean",
            method_version="northstar-v2",
            components=(component,),
            clamp="reject",
        )
    assert WeightedMeanRequest(
        method="weighted_mean",
        method_version="northstar-v2",
        components=(component,),
        clamp="clamp",
    )


def test_should_require_an_explicit_clamp_policy_for_every_request() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError):
        WeightedMeanRequest(
            method="weighted_mean", method_version="northstar-v2", components=(_component(),)
        )
    with pytest.raises(ContractValidationError):
        AdditiveRequest(method="additive", method_version="edge-v1", terms=(_term(),))
    with pytest.raises(ContractValidationError):
        MinimumRequest(
            method="minimum", method_version="alma-v1", components=(_component(weight=None),)
        )


def test_should_support_both_explicit_clamp_policies() -> None:
    # Given / When
    rejected = WeightedMeanRequest(
        method="weighted_mean",
        method_version="northstar-v2",
        components=(_component(),),
        clamp="reject",
    )
    clamped = WeightedMeanRequest(
        method="weighted_mean",
        method_version="northstar-v2",
        components=(_component(),),
        clamp="clamp",
    )

    # Then
    assert rejected.clamp is ClampPolicy.REJECT
    assert clamped.clamp is ClampPolicy.CLAMP


def test_should_canonicalize_a_forged_valid_clamp_member() -> None:
    # Given a StrEnum-shaped ClampPolicy that is not a declared member
    forged = str.__new__(ClampPolicy, "clamp")
    # When it crosses a score-request boundary
    request = WeightedMeanRequest(
        method="weighted_mean",
        method_version="northstar-v2",
        components=(_component(),),
        clamp=forged,
    )
    # Then the model stores only the exact canonical enum member
    assert request.clamp is ClampPolicy.CLAMP


def test_should_reject_a_forged_unknown_clamp_member() -> None:
    # Given a forged ClampPolicy carrying an undeclared value
    forged = str.__new__(ClampPolicy, "sometimes")
    # When it crosses a score-request boundary
    with pytest.raises(ContractValidationError) as caught:
        WeightedMeanRequest(
            method="weighted_mean",
            method_version="northstar-v2",
            components=(_component(),),
            clamp=forged,
        )
    # Then validation fails through the stable public code
    assert caught.value.code == ContractCode.INVALID_CLAMP_POLICY.value


@pytest.mark.parametrize("coefficient", [-1, -0.1])
def test_should_reject_negative_additive_coefficients(coefficient: float) -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_coefficient"):
        AdditiveTerm(
            id="semantic",
            label="Semantic",
            value=0.8,
            coefficient=coefficient,
            operation=Operation.ADD,
        )


def test_should_require_explicit_additive_operations() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError):
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
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        AdditiveTerm(id="term", label="Term", value=bad, coefficient=1, operation="add")
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        AdditiveRequest(
            method="additive",
            method_version="edge-v1",
            terms=(_term(),),
            intercept=bad,
            clamp="reject",
        )


def test_should_require_nonempty_unique_additive_terms() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.empty_terms"):
        AdditiveRequest(method="additive", method_version="edge-v1", terms=(), clamp="reject")
    with pytest.raises(ContractValidationError, match=r"assay\.duplicate_identifier"):
        AdditiveRequest(
            method="additive",
            method_version="edge-v1",
            terms=(_term(), _term()),
            clamp="reject",
        )


def test_should_require_nonempty_unique_minimum_components() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.empty_components"):
        MinimumRequest(method="minimum", method_version="alma-v1", components=(), clamp="reject")
    with pytest.raises(ContractValidationError, match=r"assay\.duplicate_identifier"):
        MinimumRequest(
            method="minimum",
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
    with pytest.raises(ContractValidationError, match=r"assay\.out_of_range"):
        MinimumRequest(
            method="minimum",
            method_version="alma-v1",
            components=(component,),
            clamp="reject",
        )


def test_should_preserve_declaration_order() -> None:
    # Given
    request = WeightedMeanRequest(
        method="weighted_mean",
        method_version="northstar-v2",
        components=(_component("zeta"), _component("alpha")),
        clamp="reject",
    )

    # When / Then
    assert tuple(item.id for item in request.components) == ("zeta", "alpha")


def test_should_round_trip_every_request_shape_through_json() -> None:
    # Given
    requests = (
        _weighted_request(),
        AdditiveRequest(
            method="additive",
            method_version="edge-v1",
            terms=(_term(),),
            intercept=0.1,
            clamp="clamp",
        ),
        MinimumRequest(
            method="minimum",
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
        score=0.13,
        interval=None,
        clamp=ClampPolicy.REJECT,
        intercept=None,
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
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        ExplainedComponent(
            id="reliability",
            raw=13,
            normalized=13 / 15,
            operation=Operation.ADD,
            coefficient=0.15,
            contribution=bad,
            contribution_interval=None,
        )
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_number"):
        ScoreResult(
            method=Method(id="weighted_mean", version="northstar-v2"),
            score=bad,
            interval=None,
            clamp=ClampPolicy.REJECT,
            intercept=None,
            components=(_explained(),),
            inputs_hash=_INPUTS_HASH,
        )


def test_should_reject_malformed_result_input_hashes() -> None:
    # Given / When / Then
    with pytest.raises(ContractValidationError, match=r"assay\.invalid_inputs_hash"):
        ScoreResult(
            method=Method(id="weighted_mean", version="northstar-v2"),
            score=0.13,
            interval=None,
            clamp=ClampPolicy.REJECT,
            intercept=None,
            components=(_explained(),),
            inputs_hash="sha256:not-a-digest",
        )


def test_should_redact_caller_values_from_contract_errors() -> None:
    # Given
    sentinel = "PII-SENTINEL-ALICE"

    # When
    with pytest.raises(ContractValidationError) as caught:
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
