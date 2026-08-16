"""Dependency-light entry point with an early historical-command boundary."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Protocol, cast

from assay.errors import AssayError, CliExtraMissing, CommandMovedToAvow, CommandReplaced

_EXIT_USAGE = 2
_MIGRATIONS = {
    "keygen": f"FAIL: {CommandMovedToAvow.code}; use `avow keygen ...`\n",
    "sign": f"FAIL: {CommandMovedToAvow.code}; use `avow sign ...`\n",
    "verify": f"FAIL: {CommandMovedToAvow.code}; use `avow verify ...`\n",
    "verify-ledger": f"FAIL: {CommandMovedToAvow.code}; use `avow ledger verify ...`\n",
    "score": f"FAIL: {CommandReplaced.code}; use `assay measure ...`\n",
    "composite": f"FAIL: {CommandReplaced.code}; use `assay compose ...`\n",
}


class _CommandRunner(Protocol):
    def __call__(self, arguments: tuple[str, ...]) -> int: ...


def _migration_message(arguments: tuple[str, ...]) -> str | None:
    if not arguments:
        return None
    return _MIGRATIONS.get(arguments[0])


def _run(arguments: tuple[str, ...]) -> int:
    try:
        module = import_module("assay._cli_app")
    except ModuleNotFoundError:
        raise CliExtraMissing from None
    runner = cast(_CommandRunner, module.run)
    return runner(arguments)


def _fail(error: AssayError) -> int:
    sys.stderr.write(f"FAIL: {error.code}\n")
    return _EXIT_USAGE


def main() -> int:
    """Reject migrated commands before loading the scoring command adapter."""
    message = _migration_message(tuple(sys.argv[1:]))
    if message is not None:
        sys.stderr.write(message)
        return _EXIT_USAGE
    try:
        return _run(tuple(sys.argv[1:]))
    except AssayError as error:
        return _fail(error)
