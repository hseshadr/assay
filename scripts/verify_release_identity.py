"""Fail closed unless one release tag identifies both immutable artifacts."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ARGUMENT_COUNT = 3
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


def _revision(revision: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", revision],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _release_commit_matches(tag: str, github_sha: str) -> bool:
    if re.fullmatch(r"[0-9a-f]{40}", github_sha) is None:
        return False
    return _revision("HEAD") == github_sha == _revision(f"refs/tags/{tag}^{{commit}}")


def _protected_main_contains(github_sha: str) -> bool:
    result = subprocess.run(  # noqa: S603
        ["git", "merge-base", "--is-ancestor", github_sha, "refs/remotes/origin/main"],  # noqa: S607
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _arguments() -> tuple[str, str] | None:
    if len(sys.argv) != _ARGUMENT_COUNT:
        print("usage: verify_release_identity.py vX.Y.Z GITHUB_SHA", file=sys.stderr)
        return None
    return sys.argv[1], sys.argv[2]


def _commit_matches(tag: str, github_sha: str) -> bool:
    try:
        return _release_commit_matches(tag, github_sha)
    except subprocess.CalledProcessError:
        return False


def _main_contains(github_sha: str) -> bool:
    try:
        return _protected_main_contains(github_sha)
    except OSError:
        return False


def _validation_error(tag: str, github_sha: str) -> str | None:
    python_version, typescript_version = _python_version(), _typescript_version()
    if not _identities_match(python_version, typescript_version, tag):
        return "release tag and artifact versions do not match"
    if not _commit_matches(tag, github_sha):
        return "release tag, commit, and artifact versions do not match"
    if not _main_contains(github_sha):
        return "release commit is not reachable from protected main"
    return None


def main() -> int:
    arguments = _arguments()
    if arguments is None:
        return 1
    tag, github_sha = arguments
    error = _validation_error(tag, github_sha)
    if error is not None:
        print(error, file=sys.stderr)
        return 1
    print(f"verified release identity: v{_typescript_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
