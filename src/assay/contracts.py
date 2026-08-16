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
    return number


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
    clamp: _ExplicitClampPolicy
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
    components: tuple[ExplainedComponent, ...]
    inputs_hash: _InputsHash

    @model_validator(mode="after")
    def _validate_components(self) -> Self:
        _require_identifiers(self.components, ContractCode.EMPTY_COMPONENTS)
        return self


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
