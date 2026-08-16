"""Behavioral contract for native-scale normalization."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from assay import ClampPolicy, Direction, NativeScale, normalize
from assay.errors import ContractCode, ContractValidationError

_SENTINEL = "PII-SENTINEL-ALICE"
_VECTOR_FIELDS = {"value", "minimum", "maximum", "direction", "clamp", "normalized"}
_VECTOR_PATH = Path("testdata/vectors/normalize.json")


def _scale(
    minimum: float = 0.0,
    maximum: float = 10.0,
    direction: Direction = Direction.HIGHER_IS_BETTER,
) -> NativeScale:
    return NativeScale(minimum=minimum, maximum=maximum, direction=direction)


def _vectors() -> list[dict[str, object]]:
    loaded = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    assert all(isinstance(row, dict) for row in loaded)
    return loaded


@pytest.mark.parametrize(
    ("value", "scale", "expected"),
    [
        (0.0, _scale(), 0.0),
        (5.0, _scale(), 0.5),
        (10.0, _scale(), 1.0),
        (-7.5, _scale(-10.0, -5.0), 0.5),
        (0.9999999999999999, _scale(0.0, 1.0), 0.9999999999999999),
    ],
)
def test_should_normalize_higher_values_on_declared_scale(
    value: float, scale: NativeScale, expected: float
) -> None:
    # Given a finite value on a higher-is-better native scale
    # When the value is normalized without clamping
    result = normalize(value, scale, ClampPolicy.REJECT)
    # Then its position is preserved exactly
    assert result == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, 1.0), (5.0, 0.5), (10.0, 0.0), (9.999999999999998, 1.7763568394002506e-16)],
)
def test_should_reverse_lower_is_better_scale(value: float, expected: float) -> None:
    # Given a finite value on a lower-is-better native scale
    scale = _scale(0.0, 10.0, Direction.LOWER_IS_BETTER)
    # When the value is normalized without clamping
    result = normalize(value, scale, ClampPolicy.REJECT)
    # Then the best endpoint maps to one and the worst to zero
    assert result == expected


def test_should_preserve_ieee_754_arithmetic_order_for_fractional_values() -> None:
    # Given decimal inputs whose binary representation exposes operation order
    scale = _scale(0.1, 0.3)
    # When the native value is normalized
    result = normalize(0.2, scale, ClampPolicy.REJECT)
    # Then Assay preserves Python's direct IEEE-754 formula without rounding
    assert result == 0.5000000000000001


@pytest.mark.parametrize(
    ("value", "direction", "expected"),
    [
        (-1e-15, Direction.HIGHER_IS_BETTER, 0.0),
        (1.0000000000000002, Direction.HIGHER_IS_BETTER, 1.0),
        (-1e-15, Direction.LOWER_IS_BETTER, 1.0),
        (1.0000000000000002, Direction.LOWER_IS_BETTER, 0.0),
    ],
)
def test_should_clamp_only_when_explicitly_requested(
    value: float, direction: Direction, expected: float
) -> None:
    # Given a value just outside its declared scale
    scale = _scale(0.0, 1.0, direction)
    # When the caller explicitly selects clamping
    result = normalize(value, scale, ClampPolicy.CLAMP)
    # Then the normalized result is bounded after the formula runs
    assert result == expected


@pytest.mark.parametrize("value", [-1e-15, 1.0000000000000002])
def test_should_reject_out_of_range_value_with_redacted_stable_code(value: float) -> None:
    # Given a finite value outside the declared native scale
    # When reject policy is selected
    with pytest.raises(ContractValidationError) as caught:
        normalize(value, _scale(0.0, 1.0), ClampPolicy.REJECT)
    # Then callers receive only the stable, value-free code
    assert caught.value.code == ContractCode.OUT_OF_RANGE.value
    assert str(caught.value) == "assay.out_of_range"
    assert _SENTINEL not in str(caught.value)


@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf, _SENTINEL])
def test_should_reject_boolean_nonfinite_and_nonnumeric_values(value: object) -> None:
    # Given an input that is not a finite real number
    # When normalization is attempted
    with pytest.raises(ContractValidationError) as caught:
        normalize(value, _scale(), ClampPolicy.REJECT)  # type: ignore[arg-type]
    # Then the error is stable and never echoes caller data
    assert caught.value.code == ContractCode.INVALID_NUMBER.value
    assert str(caught.value) == "assay.invalid_number"
    assert _SENTINEL not in str(caught.value)


def test_should_reject_a_forged_invalid_scale() -> None:
    # Given a model instance that bypassed construction-time scale validation
    invalid = NativeScale.model_construct(
        minimum=1.0, maximum=1.0, direction=Direction.HIGHER_IS_BETTER
    )
    # When normalization revalidates the public boundary
    with pytest.raises(ContractValidationError) as caught:
        normalize(1.0, invalid, ClampPolicy.REJECT)
    # Then the scale failure remains a stable domain error
    assert caught.value.code == ContractCode.INVALID_SCALE.value


def test_should_reject_nonfinite_intermediate_arithmetic() -> None:
    # Given finite endpoints whose subtraction overflows to infinity
    scale = _scale(-1e308, 1e308)
    # When normalization computes the direct declared formula
    with pytest.raises(ContractValidationError) as caught:
        normalize(0.0, scale, ClampPolicy.REJECT)
    # Then no non-finite result crosses the public boundary
    assert caught.value.code == ContractCode.INVALID_NUMBER.value


def test_should_reject_an_invalid_clamp_policy() -> None:
    # Given a caller value outside the ClampPolicy contract
    # When normalization is attempted
    with pytest.raises(ContractValidationError) as caught:
        normalize(5.0, _scale(), "clamp")  # type: ignore[arg-type]
    # Then the policy failure has its stable code
    assert caught.value.code == ContractCode.INVALID_CLAMP_POLICY.value


def test_should_ship_nonempty_language_neutral_vectors_with_exact_shape() -> None:
    # Given the committed normalization vectors
    vectors = _vectors()
    # When their portable schema is inspected
    field_sets = [set(row) for row in vectors]
    # Then every row is executable and contains only the six declared fields
    assert len(vectors) > 0
    assert field_sets == [_VECTOR_FIELDS] * len(vectors)


def test_should_replay_every_committed_normalization_vector() -> None:
    # Given each literal committed vector
    for row in _vectors():
        scale = NativeScale(
            minimum=float(row["minimum"]),
            maximum=float(row["maximum"]),
            direction=Direction(str(row["direction"])),
        )
        # When its declared inputs are normalized through the public API
        actual = normalize(float(row["value"]), scale, ClampPolicy(str(row["clamp"])))
        # Then the exact IEEE-754 result matches the language-neutral fixture
        assert actual == row["normalized"]
