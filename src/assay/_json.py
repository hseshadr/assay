"""Dependency-light JSON decoding that rejects ambiguous object members."""

from __future__ import annotations

import json

from assay.errors import AssayError, ContractCode, ContractValidationError

type JsonData = str | bytes | bytearray


class _DuplicateMemberError(Exception):
    """Private control flow for a repeated decoded object key."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateMemberError
        result[key] = value
    return result


def decode_json(data: JsonData, invalid_error: type[AssayError]) -> object:
    """Decode one JSON value without last-wins member collapse or raw exceptions."""
    error: AssayError
    try:
        return json.loads(data, object_pairs_hook=_unique_object)
    except _DuplicateMemberError:
        error = ContractValidationError(ContractCode.DUPLICATE_FIELD)
    except (ValueError, UnicodeDecodeError, TypeError, RecursionError):
        error = invalid_error()
    raise error from None
