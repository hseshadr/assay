"""Fail closed unless one release tag identifies both immutable artifacts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
_ARGUMENT_COUNT = 3
_CORE = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
_STABLE = re.compile(rf"^{_CORE}$")
_PYTHON_PRERELEASE = re.compile(rf"^({_CORE})\.dev(0|[1-9]\d*)$")
_NPM_PRERELEASE = re.compile(rf"^({_CORE})-dev\.(0|[1-9]\d*)$")


class CheckRun(BaseModel):
    """The hosted check fields needed for exact release eligibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    head_sha: str
    conclusion: str | None


class HostedPayload(BaseModel):
    """Exact remote identities and hosted checks observed from GitHub."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    main_sha: str
    tag_sha: str
    check_runs: tuple[CheckRun, ...]


def validate_hosted_eligibility(payload: str, expected_sha: str) -> None:
    """Require current main, tag, expected SHA, and one green Dagger check."""
    observed = HostedPayload.model_validate_json(payload)
    valid = (_valid_sha(expected_sha), _identities_match_hosted(observed, expected_sha))
    if not all(valid) or not _one_green_dagger(observed, expected_sha):
        raise ValueError("exact main, tag, and one green Dagger check required")


def _valid_sha(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _identities_match_hosted(observed: HostedPayload, expected_sha: str) -> bool:
    return len({observed.main_sha, observed.tag_sha, expected_sha}) == 1


def _one_green_dagger(observed: HostedPayload, expected_sha: str) -> bool:
    matching = tuple(run for run in observed.check_runs if run.name == "Dagger")
    return len(matching) == 1 and _green_check(matching[0], expected_sha)


def _green_check(run: CheckRun, expected_sha: str) -> bool:
    return run.head_sha == expected_sha and run.conclusion == "success"


def _github_json(url: str, token: str) -> dict[str, object]:
    request = Request(  # noqa: S310 - URL is built from the fixed GitHub API origin.
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("GitHub release evidence is malformed")
    return payload


def _check_run(value: object) -> CheckRun:
    if not isinstance(value, dict):
        raise ValueError("GitHub release evidence is malformed")
    fields = ("name", "head_sha", "conclusion")
    return CheckRun.model_validate({field: value.get(field) for field in fields})


def _hosted_payload(repository: str, tag: str, sha: str, token: str) -> str:
    root = f"https://api.github.com/repos/{repository}/commits"
    main = _github_json(f"{root}/main", token)
    tagged = _github_json(f"{root}/{quote(tag, safe='')}", token)
    checks = _github_json(f"{root}/{sha}/check-runs?per_page=100", token)
    runs = checks.get("check_runs")
    if not isinstance(main.get("sha"), str) or not isinstance(tagged.get("sha"), str):
        raise ValueError("GitHub release evidence is malformed")
    if not isinstance(runs, list):
        raise ValueError("GitHub release evidence is malformed")
    return HostedPayload(
        main_sha=str(main["sha"]),
        tag_sha=str(tagged["sha"]),
        check_runs=tuple(_check_run(run) for run in runs),
    ).model_dump_json()


def _github_main() -> int:
    if len(sys.argv) != 5:  # noqa: PLR2004
        print("usage: verify_release_identity.py github OWNER/REPO TAG SHA", file=sys.stderr)
        return 1
    repository, tag, sha = sys.argv[2:]
    token = os.environ.get("GITHUB_TOKEN", "")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", repository) is None or not token:
        print("hosted release evidence is unavailable", file=sys.stderr)
        return 1
    try:
        validate_hosted_eligibility(_hosted_payload(repository, tag, sha, token), sha)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


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
    return _revision("refs/remotes/origin/main") == github_sha


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
    except (OSError, subprocess.CalledProcessError):
        return False


def _validation_error(tag: str, github_sha: str) -> str | None:
    python_version, typescript_version = _python_version(), _typescript_version()
    if not _identities_match(python_version, typescript_version, tag):
        return "release tag and artifact versions do not match"
    if not _commit_matches(tag, github_sha):
        return "release tag, commit, and artifact versions do not match"
    if not _main_contains(github_sha):
        return "release commit is not exact protected main"
    return None


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "github":
        return _github_main()
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
