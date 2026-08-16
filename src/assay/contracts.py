"""Immutable, JSON-safe contracts for portable score composition."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, NoReturn, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    ValidationError,
    model_serializer,
    model_validator,
)
from pydantic.config import ExtraValues
from pydantic.fields import FieldInfo

from assay.errors import ContractCode, ContractValidationError

__all__ = [
    "AdditiveRequest",
    "AdditiveTerm",
    "ClampPolicy",
    "Component",
    "Direction",
    "ExplainedComponent",
    "Interval",
    "Method",
    "MinimumRequest",
    "NativeScale",
    "Operation",
    "ScoreRequest",
    "ScoreResult",
    "WeightedMeanRequest",
    "parse_request",
    "parse_request_json",
]

_MODEL_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    hide_input_in_errors=True,
    populate_by_name=True,
    revalidate_instances="always",
    serialize_by_alias=True,
)
_STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_IDENTIFIER_LENGTH = 128
_MAX_LABEL_LENGTH = 256
_SURROGATE_MIN = 0xD800
_SURROGATE_MAX = 0xDFFF
_JsonData = str | bytes | bytearray
_OptionalBool = bool | None
_OptionalExtra = ExtraValues | None
_ValidationOptions = tuple[
    _OptionalBool, _OptionalExtra, object | None, _OptionalBool, _OptionalBool
]
_PythonValidationOptions = tuple[
    _OptionalBool,
    _OptionalExtra,
    _OptionalBool,
    object | None,
    _OptionalBool,
    _OptionalBool,
]


class Direction(StrEnum):
    """Whether larger or smaller native values represent a better outcome."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class ClampPolicy(StrEnum):
    """How a declared boundary handles an out-of-range value."""

    REJECT = "reject"
    CLAMP = "clamp"


class Operation(StrEnum):
    """The explicit sign of an additive term."""

    ADD = "add"
    SUBTRACT = "subtract"


def _fail(code: ContractCode) -> NoReturn:
    raise ContractValidationError(code) from None


def _decode_json(data: _JsonData) -> object:
    error: ContractValidationError
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError, TypeError):
        error = ContractValidationError(ContractCode.INVALID_CONTRACT)
    raise error from None


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(ContractCode.INVALID_NUMBER)
    try:
        number = float(value)
    except OverflowError:
        number = math.nan
    if not math.isfinite(number):
        _fail(ContractCode.INVALID_NUMBER)
    return _canonical_zero(number)


def _canonical_zero(value: float) -> float:
    return 0.0 if value == 0.0 else value


def _positive(value: object) -> float:
    number = _finite(value)
    if number <= 0:
        _fail(ContractCode.INVALID_WEIGHT)
    return number


def _nonnegative(value: object) -> float:
    number = _finite(value)
    if number < 0:
        _fail(ContractCode.INVALID_COEFFICIENT)
    return number


def _stable_identifier(value: object) -> str:
    if not isinstance(value, str) or len(value) > _MAX_IDENTIFIER_LENGTH:
        _fail(ContractCode.INVALID_IDENTIFIER)
    if _STABLE_ID.fullmatch(value) is None:
        _fail(ContractCode.INVALID_IDENTIFIER)
    return value


def _contains_surrogate(value: str) -> bool:
    return any(_SURROGATE_MIN <= ord(character) <= _SURROGATE_MAX for character in value)


def _label(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(ContractCode.INVALID_LABEL)
    if len(value) > _MAX_LABEL_LENGTH:
        _fail(ContractCode.INVALID_LABEL)
    if _contains_surrogate(value):
        _fail(ContractCode.INVALID_TEXT)
    return value


def _inputs_hash(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(ContractCode.INVALID_INPUTS_HASH)
    return value


def _direction(value: object) -> Direction:
    if isinstance(value, str):
        try:
            return Direction(str(value))
        except ValueError:
            pass
    _fail(ContractCode.INVALID_DIRECTION)


def _clamp_policy(value: object) -> ClampPolicy:
    if isinstance(value, str):
        try:
            return ClampPolicy(str(value))
        except ValueError:
            pass
    _fail(ContractCode.INVALID_CLAMP_POLICY)


def _operation(value: object) -> Operation:
    if isinstance(value, Operation):
        return value
    if isinstance(value, str):
        try:
            return Operation(value)
        except ValueError:
            pass
    _fail(ContractCode.INVALID_OPERATION)


def _method_identifier(value: object) -> str:
    allowed = {"weighted_mean", "additive", "minimum"}
    if isinstance(value, str) and value in allowed:
        return value
    _fail(ContractCode.INVALID_METHOD)


_FiniteNumber = Annotated[float, BeforeValidator(_finite)]
_PositiveWeight = Annotated[float, BeforeValidator(_positive)]
_NonnegativeCoefficient = Annotated[float, BeforeValidator(_nonnegative)]
_StableIdentifier = Annotated[str, BeforeValidator(_stable_identifier)]
_DisplayLabel = Annotated[str, BeforeValidator(_label)]
_ExplicitDirection = Annotated[Direction, BeforeValidator(_direction)]
_ExplicitClampPolicy = Annotated[ClampPolicy, BeforeValidator(_clamp_policy)]
_ExplicitOperation = Annotated[Operation, BeforeValidator(_operation)]
_InputsHash = Annotated[str, BeforeValidator(_inputs_hash)]
_MethodIdentifier = Annotated[
    Literal["weighted_mean", "additive", "minimum"],
    BeforeValidator(_method_identifier),
]


def _accepted_names(name: str, field: FieldInfo) -> tuple[str, ...]:
    if isinstance(field.alias, str):
        return (name, field.alias)
    return (name,)


def _allowed_names(fields: Mapping[str, FieldInfo]) -> frozenset[str]:
    return frozenset(
        accepted for name, field in fields.items() for accepted in _accepted_names(name, field)
    )


def _selected_names(
    name: str, field: FieldInfo, by_alias: _OptionalBool, by_name: _OptionalBool
) -> tuple[str, ...]:
    if not isinstance(field.alias, str):
        return (name,)
    names = (name,) if by_name is not False else ()
    return (*names, field.alias) if by_alias is not False else names


def _selected_allowed_names(
    fields: Mapping[str, FieldInfo], by_alias: _OptionalBool, by_name: _OptionalBool
) -> frozenset[str]:
    return frozenset(
        accepted
        for name, field in fields.items()
        for accepted in _selected_names(name, field, by_alias, by_name)
    )


def _contains_only_known_fields(
    data: Mapping[object, object], fields: Mapping[str, FieldInfo]
) -> bool:
    allowed = _allowed_names(fields)
    return all(isinstance(key, str) and key in allowed for key in data)


def _contains_required_fields(
    data: Mapping[object, object], fields: Mapping[str, FieldInfo]
) -> bool:
    return all(
        not field.is_required() or any(name in data for name in _accepted_names(field_name, field))
        for field_name, field in fields.items()
    )


def _contains_alias_duplicate(
    data: Mapping[object, object], fields: Mapping[str, FieldInfo]
) -> bool:
    return any(
        isinstance(field.alias, str)
        and field.alias != name
        and field.alias in data
        and name in data
        for name, field in fields.items()
    )


def _require_mapping(data: object) -> Mapping[object, object]:
    if not isinstance(data, Mapping):
        _fail(ContractCode.INVALID_OBJECT)
    return data


def _require_known_fields(data: Mapping[object, object], fields: Mapping[str, FieldInfo]) -> None:
    if not _contains_only_known_fields(data, fields):
        _fail(ContractCode.UNKNOWN_FIELD)


def _require_selected_fields(
    data: Mapping[object, object],
    fields: Mapping[str, FieldInfo],
    by_alias: _OptionalBool,
    by_name: _OptionalBool,
) -> None:
    allowed = _selected_allowed_names(fields, by_alias, by_name)
    if not all(isinstance(key, str) and key in allowed for key in data):
        _fail(ContractCode.UNKNOWN_FIELD)


def _require_no_alias_duplicates(
    data: Mapping[object, object], fields: Mapping[str, FieldInfo]
) -> None:
    if _contains_alias_duplicate(data, fields):
        _fail(ContractCode.DUPLICATE_FIELD)


def _require_method(data: Mapping[object, object], expected: str | None) -> None:
    if expected is not None and data.get("method") != expected:
        _fail(ContractCode.INVALID_METHOD)


def _require_required_fields(
    data: Mapping[object, object], fields: Mapping[str, FieldInfo]
) -> None:
    if not _contains_required_fields(data, fields):
        _fail(ContractCode.MISSING_FIELD)


def _require_alias_config(by_alias: _OptionalBool, by_name: _OptionalBool) -> None:
    if by_alias is False and by_name is not True:
        _fail(ContractCode.INVALID_ALIAS_CONFIG)


class _ContractModel(BaseModel):
    """Shared fail-closed shape validation for every public JSON model."""

    model_config = _MODEL_CONFIG
    _expected_method: ClassVar[str | None] = None

    def __init__(self, **data: object) -> None:
        error: ContractValidationError
        try:
            super().__init__(**data)
            return
        except ValidationError:
            error = ContractValidationError(ContractCode.INVALID_CONTRACT)
        raise error from None

    @model_validator(mode="before")
    @classmethod
    def _validate_input_shape(cls, data: object) -> object:
        if isinstance(data, cls):
            return data
        mapping = _require_mapping(data)
        _require_no_alias_duplicates(mapping, cls.model_fields)
        _require_known_fields(mapping, cls.model_fields)
        _require_method(mapping, cls._expected_method)
        _require_required_fields(mapping, cls.model_fields)
        return mapping

    @classmethod
    def model_validate(
        cls,
        obj: object,
        *,
        strict: _OptionalBool = None,
        extra: _OptionalExtra = None,
        from_attributes: _OptionalBool = None,
        context: object | None = None,
        by_alias: _OptionalBool = None,
        by_name: _OptionalBool = None,
    ) -> Self:
        _require_alias_config(by_alias, by_name)
        cls._validate_selected_input(obj, by_alias, by_name)
        options = (strict, extra, from_attributes, context, by_alias, by_name)
        return cls._validate_python(obj, options)

    @classmethod
    def _validate_selected_input(
        cls, obj: object, by_alias: _OptionalBool, by_name: _OptionalBool
    ) -> None:
        if not isinstance(obj, Mapping):
            return
        _require_no_alias_duplicates(obj, cls.model_fields)
        _require_selected_fields(obj, cls.model_fields, by_alias, by_name)

    @classmethod
    def _validate_python(cls, obj: object, options: _PythonValidationOptions) -> Self:
        strict, extra, from_attributes, context, by_alias, by_name = options
        try:
            return super().model_validate(
                obj,
                strict=strict,
                extra=extra,
                from_attributes=from_attributes,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except ValidationError:
            error = ContractValidationError(ContractCode.INVALID_CONTRACT)
        raise error from None

    @classmethod
    def model_validate_json(
        cls,
        data: _JsonData,
        *,
        strict: _OptionalBool = None,
        extra: _OptionalExtra = None,
        context: object | None = None,
        by_alias: _OptionalBool = None,
        by_name: _OptionalBool = None,
    ) -> Self:
        options = (strict, extra, context, by_alias, by_name)
        return cls._validate_decoded_json(data, options)

    @classmethod
    def _validate_decoded_json(cls, data: _JsonData, options: _ValidationOptions) -> Self:
        strict, extra, context, by_alias, by_name = options
        return cls.model_validate(
            _decode_json(data),
            strict=strict,
            extra=extra,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )

    def model_copy(self, *, update: Mapping[str, object] | None = None, deep: bool = False) -> Self:
        candidate = super().model_copy(update=update, deep=deep)
        return type(self).model_validate(candidate)

    @model_serializer(mode="wrap")
    def _serialize_validated(self, handler: SerializerFunctionWrapHandler) -> object:
        validated = type(self).model_validate(self)
        return handler(validated)


class NativeScale(_ContractModel):
    """The declared native range and direction for one measurement."""

    model_config = _MODEL_CONFIG

    minimum: _FiniteNumber
    maximum: _FiniteNumber
    direction: _ExplicitDirection

    @model_validator(mode="after")
    def _require_increasing_bounds(self) -> Self:
        if self.maximum <= self.minimum:
            _fail(ContractCode.INVALID_SCALE)
        return self


class Interval(_ContractModel):
    """A finite uncertainty interval; deterministic values use ``None``."""

    model_config = _MODEL_CONFIG

    low: _FiniteNumber
    high: _FiniteNumber

    @model_validator(mode="after")
    def _require_ordered_bounds(self) -> Self:
        if self.high <= self.low:
            _fail(ContractCode.INVALID_INTERVAL)
        return self


class Component(_ContractModel):
    """A measurement on its declared native scale."""

    model_config = _MODEL_CONFIG

    id: _StableIdentifier
    label: _DisplayLabel
    value: _FiniteNumber
    scale: NativeScale
    interval: Interval | None = None
    weight: _PositiveWeight | None = None


class AdditiveTerm(_ContractModel):
    """One explicitly signed term in a left-to-right additive score."""

    model_config = _MODEL_CONFIG

    id: _StableIdentifier
    label: _DisplayLabel
    value: _FiniteNumber
    coefficient: _NonnegativeCoefficient
    operation: _ExplicitOperation
    interval: Interval | None = None


class ExplainedComponent(_ContractModel):
    """The contribution of one declared input to a composed result."""

    model_config = _MODEL_CONFIG

    id: _StableIdentifier
    raw: _FiniteNumber
    normalized: _FiniteNumber | None
    operation: _ExplicitOperation
    coefficient: _NonnegativeCoefficient
    contribution: _FiniteNumber
    contribution_interval: Interval | None


class Method(_ContractModel):
    """The closed combiner identity and caller-declared method version."""

    model_config = _MODEL_CONFIG

    id: _MethodIdentifier
    version: _StableIdentifier


_IdentifiedContracts = (
    tuple[Component, ...] | tuple[AdditiveTerm, ...] | tuple[ExplainedComponent, ...]
)


def _require_identifiers(items: _IdentifiedContracts, empty_code: ContractCode) -> None:
    if not items:
        _fail(empty_code)
    identifiers = tuple(item.id for item in items)
    if len(identifiers) != len(set(identifiers)):
        _fail(ContractCode.DUPLICATE_IDENTIFIER)


def _component_is_in_scale(component: Component) -> bool:
    values = [component.value]
    if component.interval is not None:
        values.extend((component.interval.low, component.interval.high))
    return all(component.scale.minimum <= value <= component.scale.maximum for value in values)


def _require_component_ranges(components: tuple[Component, ...], clamp: ClampPolicy) -> None:
    if clamp is not ClampPolicy.REJECT:
        return
    if not all(_component_is_in_scale(component) for component in components):
        _fail(ContractCode.OUT_OF_RANGE)


class WeightedMeanRequest(_ContractModel):
    """A positive weighted mean of normalized components."""

    model_config = _MODEL_CONFIG
    _expected_method: ClassVar[str | None] = "weighted_mean"

    method: Literal["weighted_mean"]
    method_version: _StableIdentifier
    components: tuple[Component, ...]
    clamp: _ExplicitClampPolicy

    @model_validator(mode="after")
    def _validate_components(self) -> Self:
        _require_identifiers(self.components, ContractCode.EMPTY_COMPONENTS)
        if any(component.weight is None for component in self.components):
            _fail(ContractCode.MISSING_WEIGHT)
        _require_component_ranges(self.components, self.clamp)
        return self


class AdditiveRequest(_ContractModel):
    """An ordered additive score with explicit term operations."""

    model_config = _MODEL_CONFIG
    _expected_method: ClassVar[str | None] = "additive"

    method: Literal["additive"]
    method_version: _StableIdentifier
    terms: tuple[AdditiveTerm, ...]
    clamp: _ExplicitClampPolicy | None
    intercept: _FiniteNumber = 0.0

    @model_validator(mode="after")
    def _validate_terms(self) -> Self:
        _require_identifiers(self.terms, ContractCode.EMPTY_TERMS)
        return self


class MinimumRequest(_ContractModel):
    """A bottleneck score selecting the first minimum normalized component."""

    model_config = _MODEL_CONFIG
    _expected_method: ClassVar[str | None] = "minimum"

    method: Literal["minimum"]
    method_version: _StableIdentifier
    components: tuple[Component, ...]
    clamp: _ExplicitClampPolicy

    @model_validator(mode="after")
    def _validate_components(self) -> Self:
        _require_identifiers(self.components, ContractCode.EMPTY_COMPONENTS)
        _require_component_ranges(self.components, self.clamp)
        return self


class ScoreResult(_ContractModel):
    """A deterministic, portable explanation of one composed score."""

    model_config = _MODEL_CONFIG

    schema_version: Literal["assay.result/v1"] = Field(default="assay.result/v1", alias="schema")
    method: Method
    score: _FiniteNumber
    interval: Interval | None = None
    clamp: _ExplicitClampPolicy | None
    intercept: _FiniteNumber | None
    components: tuple[ExplainedComponent, ...]
    inputs_hash: _InputsHash
    selected_component_id: _StableIdentifier | None = None

    @model_validator(mode="after")
    def _validate_components(self) -> Self:
        _require_identifiers(self.components, ContractCode.EMPTY_COMPONENTS)
        _require_result_invariants(self)
        return self


_ContributionBounds = tuple[float, float] | None


def _require_result(condition: bool) -> None:
    if not condition:
        _fail(ContractCode.INVALID_RESULT)


def _result_number(value: float) -> float:
    if not math.isfinite(value):
        _fail(ContractCode.INVALID_RESULT)
    return 0.0 if value == 0.0 else value


def _result_add(values: tuple[float, ...], initial: float = 0.0) -> float:
    total = initial
    for value in values:
        total = _result_number(total + value)
    return total


def _row_bounds(row: ExplainedComponent) -> tuple[float, float]:
    if row.contribution_interval is None:
        return row.contribution, row.contribution
    return row.contribution_interval.low, row.contribution_interval.high


def _matches_interval(actual: Interval | None, expected: _ContributionBounds) -> bool:
    if expected is None or expected[0] == expected[1]:
        return actual is None
    return actual is not None and (actual.low, actual.high) == expected


def _sum_interval(rows: tuple[ExplainedComponent, ...]) -> _ContributionBounds:
    if not _has_contribution_intervals(rows):
        return None
    lows, highs = zip(*(_row_bounds(row) for row in rows), strict=True)
    return _result_add(lows), _result_add(highs)


def _bounded_row(row: ExplainedComponent, maximum: float) -> bool:
    interval = row.contribution_interval
    return interval is None or 0.0 <= interval.low < interval.high <= maximum


def _has_contribution_intervals(rows: tuple[ExplainedComponent, ...]) -> bool:
    return any(row.contribution_interval is not None for row in rows)


def _weighted_row(row: ExplainedComponent) -> bool:
    normalized = row.normalized
    if normalized is None:
        return False
    contribution = _result_number(normalized * row.coefficient)
    shape = row.operation is Operation.ADD and 0.0 < row.coefficient <= 1.0
    return shape and 0.0 <= normalized <= 1.0 and row.contribution == contribution


def _require_weighted_result(result: ScoreResult) -> None:
    rows = result.components
    _require_result(_weighted_shape(result))
    _require_result(_valid_weighted_rows(rows))
    _require_result(result.score == _result_add(tuple(row.contribution for row in rows)))
    _require_result(_matches_interval(result.interval, _sum_interval(rows)))


def _weighted_shape(result: ScoreResult) -> bool:
    return (
        result.selected_component_id is None
        and result.intercept is None
        and result.clamp is not None
    )


def _valid_weighted_rows(rows: tuple[ExplainedComponent, ...]) -> bool:
    return all(_weighted_row(row) and _bounded_row(row, row.coefficient) for row in rows)


def _additive_row(row: ExplainedComponent) -> bool:
    contribution = _result_number(row.raw * row.coefficient)
    return row.normalized is None and row.contribution == contribution


def _signed_add(total: float, row: ExplainedComponent, value: float) -> float:
    if row.operation is Operation.ADD:
        return _result_number(total + value)
    return _result_number(total - value)


def _additive_point(result: ScoreResult) -> float:
    if result.intercept is None:  # pragma: no cover - guarded by the result invariant
        _fail(ContractCode.INVALID_RESULT)
    total = result.intercept
    for row in result.components:
        total = _signed_add(total, row, row.contribution)
    return _final_result(total, result.clamp)


def _final_result(value: float, policy: ClampPolicy | None) -> float:
    if policy is None:
        return value
    if policy is ClampPolicy.CLAMP:
        return 0.0 if value <= 0.0 else min(1.0, value)
    _require_result(0.0 <= value <= 1.0)
    return value


def _additive_interval(result: ScoreResult) -> _ContributionBounds:
    if not _has_contribution_intervals(result.components):
        return None
    if result.intercept is None:  # pragma: no cover - guarded by the result invariant
        _fail(ContractCode.INVALID_RESULT)
    low = high = result.intercept
    for row in result.components:
        low, high = _advance_result_bounds(low, high, row)
    return _final_result(low, result.clamp), _final_result(high, result.clamp)


def _advance_result_bounds(low: float, high: float, row: ExplainedComponent) -> tuple[float, float]:
    row_low, row_high = _row_bounds(row)
    if row.operation is Operation.ADD:
        return _signed_add(low, row, row_low), _signed_add(high, row, row_high)
    return _signed_add(low, row, row_high), _signed_add(high, row, row_low)


def _require_additive_result(result: ScoreResult) -> None:
    shape = result.selected_component_id is None and result.intercept is not None
    _require_result(shape and all(_additive_row(row) for row in result.components))
    _require_result(result.score == _additive_point(result))
    _require_result(_matches_interval(result.interval, _additive_interval(result)))


def _minimum_row(row: ExplainedComponent) -> bool:
    normalized = row.normalized
    if normalized is None:
        return False
    shape = row.operation is Operation.ADD and row.coefficient == 1.0
    return shape and 0.0 <= normalized <= 1.0 and row.contribution == normalized


def _minimum_interval(rows: tuple[ExplainedComponent, ...]) -> _ContributionBounds:
    if not _has_contribution_intervals(rows):
        return None
    bounds = tuple(_row_bounds(row) for row in rows)
    return _minimum_lows(bounds), _minimum_highs(bounds)


def _minimum_lows(bounds: tuple[tuple[float, float], ...]) -> float:
    return min(low for low, _ in bounds)


def _minimum_highs(bounds: tuple[tuple[float, float], ...]) -> float:
    return min(high for _, high in bounds)


def _require_minimum_result(result: ScoreResult) -> None:
    rows = result.components
    shape = result.clamp is not None and result.intercept is None
    _require_result(shape and all(_minimum_row(row) for row in rows))
    _require_result(all(_bounded_row(row, 1.0) for row in rows))
    selected = min(rows, key=lambda row: row.contribution)
    _require_result(result.selected_component_id == selected.id)
    _require_result(result.score == selected.normalized == selected.contribution)
    _require_result(_matches_interval(result.interval, _minimum_interval(rows)))


def _require_result_invariants(result: ScoreResult) -> None:
    if result.method.id == "weighted_mean":
        _require_weighted_result(result)
    elif result.method.id == "additive":
        _require_additive_result(result)
    else:
        _require_minimum_result(result)


ScoreRequest = Annotated[
    WeightedMeanRequest | AdditiveRequest | MinimumRequest,
    Field(discriminator="method"),
]
_REQUEST_ADAPTER: TypeAdapter[ScoreRequest] = TypeAdapter(ScoreRequest)
_METHODS = frozenset(("weighted_mean", "additive", "minimum"))


def _validate_request_method(data: object) -> object:
    if not isinstance(data, Mapping):
        _fail(ContractCode.INVALID_METHOD)
    method = data.get("method")
    if not isinstance(method, str) or method not in _METHODS:
        _fail(ContractCode.INVALID_METHOD)
    return data


def parse_request(data: object) -> ScoreRequest:
    """Parse an in-memory request without exposing Pydantic's internal errors."""
    prepared = _validate_request_method(data)
    error: ContractValidationError
    try:
        return _REQUEST_ADAPTER.validate_python(prepared)
    except ValidationError:
        error = ContractValidationError(ContractCode.INVALID_CONTRACT)
    raise error from None


def parse_request_json(data: _JsonData) -> ScoreRequest:
    """Parse a JSON request into its explicitly discriminated request type."""
    return parse_request(_decode_json(data))
