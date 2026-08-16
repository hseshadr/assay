"""Fail closed unless one release tag identifies both immutable artifacts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ARGUMENT_COUNT = 2
_CORE = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
_STABLE = re.compile(rf"^{_CORE}$")
_PYTHON_PRERELEASE = re.compile(rf"^({_CORE})\.dev(0|[1-9]\d*)$")
_NPM_PRERELEASE = re.compile(rf"^({_CORE})-dev\.(0|[1-9]\d*)$")


def _python_version() -> str:
    source = (ROOT / "src/assay/_version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', source, re.MULTILINE)
    if match is None:
        raise ValueError("Python artifact version is missing")
    return match.group(1)


def _typescript_version() -> str:
    package = json.loads((ROOT / "ts/package.json").read_text(encoding="utf-8"))
    version = package.get("version") if isinstance(package, dict) else None
    if not isinstance(version, str):
        raise ValueError("TypeScript artifact version is missing")
    return version


def _npm_spelling(python_version: str) -> str | None:
    if _STABLE.fullmatch(python_version) is not None:
        return python_version
    match = _PYTHON_PRERELEASE.fullmatch(python_version)
    if match is None:
        return None
    return f"{match.group(1)}-dev.{match.group(2)}"


def _identities_match(python_version: str, npm_version: str, tag: str) -> bool:
    normalized = _npm_spelling(python_version)
    npm_supported = _STABLE.fullmatch(npm_version) or _NPM_PRERELEASE.fullmatch(npm_version)
    return normalized == npm_version and npm_supported is not None and tag == f"v{npm_version}"


def main() -> int:
    if len(sys.argv) != _ARGUMENT_COUNT:
        print("usage: verify_release_identity.py vX.Y.Z", file=sys.stderr)
        return 1
    python_version, typescript_version = _python_version(), _typescript_version()
    expected = f"v{typescript_version}"
    if not _identities_match(python_version, typescript_version, sys.argv[1]):
        print("release tag and artifact versions do not match", file=sys.stderr)
        return 1
    print(f"verified release identity: {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
