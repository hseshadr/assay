"""Value-redacted input and output primitives for the command adapter."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Final, Protocol

from assay.errors import CliInputInvalid, CliOutputInvalid

_MAX_INPUT_BYTES: Final[int] = 1_048_576
_READ_CHUNK_BYTES: Final[int] = 65_536


class JsonModel(Protocol):
    """The one serialization operation needed by the CLI."""

    def model_dump_json(self, *, by_alias: bool) -> str: ...


def _read_chunks(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := os.read(descriptor, _READ_CHUNK_BYTES):
        total += len(chunk)
        if total > _MAX_INPUT_BYTES:
            raise CliInputInvalid
        chunks.append(chunk)
    return b"".join(chunks)


def _read_regular(descriptor: int) -> bytes:
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        raise CliInputInvalid
    return _read_chunks(descriptor)


def read_input(path: str) -> bytes:
    """Read one bounded regular file through a single already-open descriptor."""
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        return _read_regular(descriptor)
    except OSError:
        raise CliInputInvalid from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def json_bytes(model: JsonModel) -> bytes:
    """Serialize exactly once and terminate the public JSON stream with one LF."""
    return model.model_dump_json(by_alias=True).encode("utf-8") + b"\n"


def _normalized_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    return unicodedata.normalize("NFC", resolved).casefold()


def _same_existing(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except OSError:
        return False


def _reject_alias(source: Path, destination: Path) -> None:
    if _same_existing(source, destination):
        raise CliOutputInvalid
    if _normalized_path(source) == _normalized_path(destination):
        raise CliOutputInvalid


def _require_destination(destination: Path) -> None:
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir():
        raise CliOutputInvalid
    if destination.is_symlink():
        raise CliOutputInvalid
    if destination.exists() and not destination.is_file():
        raise CliOutputInvalid


def _flush_file(descriptor: int, payload: bytes) -> None:
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _flush_parent(parent: Path) -> None:
    descriptor = os.open(parent, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install(payload: bytes, destination: Path) -> None:
    descriptor, stage = tempfile.mkstemp(prefix=".assay-", dir=destination.parent)
    try:
        _flush_file(descriptor, payload)
        os.replace(stage, destination)
        _flush_parent(destination.parent)
    finally:
        Path(stage).unlink(missing_ok=True)


def _write_file(payload: bytes, destination: str, source: str) -> None:
    output = Path(destination)
    try:
        _reject_alias(Path(source), output)
        _require_destination(output)
        _install(payload, output)
    except OSError:
        raise CliOutputInvalid from None


def write_output(payload: bytes, destination: str | None, source: str) -> None:
    """Write exact bytes to stdout or install them crash-safely beside the destination."""
    if destination is not None:
        _write_file(payload, destination, source)
        return
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
