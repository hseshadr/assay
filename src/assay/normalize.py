"""Pure normalization from a declared native scale to zero through one."""

from __future__ import annotations

import math
from typing import Final, NoReturn

from assay.contracts import ClampPolicy, Direction, NativeScale
from assay.errors import ContractCode, ContractValidationError

__all__ = ["normalize"]

_NORMALIZED_MIN: Final = 0.0
_NORMALIZED_MAX: Final = 1.0


def _fail(code: ContractCode) -> NoReturn:
    raise ContractValidationError(code) from None


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(ContractCode.INVALID_NUMBER)
    try:
        number = float(value)
    except OverflowError:
        _fail(ContractCode.INVALID_NUMBER)
    if not math.isfinite(number):
        _fail(ContractCode.INVALID_NUMBER)
    return number


def _formula(value: float, scale: NativeScale) -> float:
    width = scale.maximum - scale.minimum
    offset = value - scale.minimum
    if scale.direction is Direction.LOWER_IS_BETTER:
        offset = scale.maximum - value
    if not math.isfinite(width) or not math.isfinite(offset):
        _fail(ContractCode.INVALID_NUMBER)
    result = offset / width
    if not math.isfinite(result):
        _fail(ContractCode.INVALID_NUMBER)
    return result


def _apply_policy(result: float, clamp: ClampPolicy) -> float:
    if not isinstance(clamp, ClampPolicy):
        _fail(ContractCode.INVALID_CLAMP_POLICY)
    if clamp is ClampPolicy.CLAMP:
        return min(_NORMALIZED_MAX, max(_NORMALIZED_MIN, result))
    if not _NORMALIZED_MIN <= result <= _NORMALIZED_MAX:
        _fail(ContractCode.OUT_OF_RANGE)
    return result


def normalize(value: float, scale: NativeScale, clamp: ClampPolicy) -> float:
    """Map one finite native value onto its declared zero-to-one scale."""
    number = _finite(value)
    validated_scale = NativeScale.model_validate(scale)
    result = _formula(number, validated_scale)
    return _apply_policy(result, clamp)
