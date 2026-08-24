"""Behavior contract for Assay's native Dagger workspace."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DAGGER = shutil.which("dagger")
RUN_DAGGER = DAGGER is not None and os.environ.get("ASSAY_DAGGER_INTEGRATION") == "1"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
EXPECTED_FUNCTIONS = frozenset(
    {
        "artifacts",
        "benchmarks",
        "distribution",
        "example",
        "mutations",
        "parity",
        "preview",
        "publish-ready",
        "python",
        "security",
        "typescript",
    }
)
EXPECTED_CHECKS = frozenset(
    f"assay:{name}" for name in EXPECTED_FUNCTIONS - {"artifacts", "preview"}
) | {"shellcheck:check"}
PRODUCTION_MIN_LINES = 100
PRODUCTION_MAX_LINES = 250
TRIGGER_MIN_LINES = 15
TRIGGER_MAX_LINES = 30


def _dagger(*arguments: str) -> subprocess.CompletedProcess[str]:
    assert DAGGER is not None
    return subprocess.run(
        (DAGGER, "--silent", *arguments),
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=900,
    )


def _plain(output: str) -> str:
    return ANSI_ESCAPE.sub("", output)


def _names(output: str) -> frozenset[str]:
    return frozenset(token for token in _plain(output).split() if token in EXPECTED_FUNCTIONS)


def _check_names(output: str) -> frozenset[str]:
    tokens = _plain(output).split()
    return frozenset(token for token in tokens if token in EXPECTED_CHECKS)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_should_keep_native_module_within_handwritten_budget() -> None:
    # Given
    root = ROOT / ".dagger/src"

    # When
    lines = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in root.rglob("*.py"))

    # Then
    assert PRODUCTION_MIN_LINES <= lines <= PRODUCTION_MAX_LINES


def test_should_use_a_thin_pinned_github_trigger() -> None:
    # Given
    workflow = ROOT / ".github/workflows/dagger.yml"

    # When
    source = workflow.read_text(encoding="utf-8")
    pins = re.findall(r"uses:\s*[^@\s]+@([^\s]+)", source)

    # Then
    assert TRIGGER_MIN_LINES <= len(source.splitlines()) <= TRIGGER_MAX_LINES
    assert pins
    assert all(re.fullmatch(r"[0-9a-f]{40}", pin) for pin in pins)
    assert 'version: "0.21.8"' in source
    assert source.count("dagger/dagger-for-github@") == 1
    assert "verb: check" in source
    isolated = ("assay:mutations", "assay:typescript", "assay:benchmarks")
    assert all(f"run: dagger check {name}" in source for name in isolated)
    positions = [source.rfind(name) for name in isolated]
    assert positions == sorted(positions)
    assert re.search(r"^\s+check:", source, re.MULTILINE) is None


def test_should_leave_trusted_publishing_outside_dagger() -> None:
    # Given
    module = ROOT / ".dagger/src/assay_dagger/main.py"

    # When
    source = module.read_text(encoding="utf-8")
    publish = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")

    # Then
    assert "dagger.Secret" not in source
    assert "id-token: write" not in source
    assert "id-token: write" in publish


def test_should_keep_dependency_and_workflow_security_inside_dagger() -> None:
    # Given / When
    source = (ROOT / ".dagger/src/assay_dagger/main.py").read_text(encoding="utf-8")

    # Then Dagger owns every repeatable security gate while Gitleaks remains external
    assert '["uv", "run", "poe", "audit"]' in source
    assert '["uv", "run", "poe", "workflow-lint"]' in source
    assert '["uv", "run", "poe", "workflow-security"]' in source
    assert "gitleaks git" not in source.lower()
    assert "gitleaks dir" not in source.lower()


def test_should_key_execution_from_a_narrow_workspace_snapshot() -> None:
    # Given / When
    source = (ROOT / ".dagger/src/assay_dagger/main.py").read_text(encoding="utf-8")

    # Then
    assert 'directory("/", include=SOURCE_INCLUDE)' in source
    assert '"QUICKSTART.md"' in source
    assert '".git/**"' not in source
    assert '"dist/**"' not in source


@pytest.mark.skipif(not RUN_DAGGER, reason="set ASSAY_DAGGER_INTEGRATION=1")
def test_should_expose_only_concrete_assay_goals() -> None:
    # Given / When
    result = _dagger("functions")

    # Then
    assert result.returncode == 0, result.stderr
    assert _names(result.stdout) == EXPECTED_FUNCTIONS


@pytest.mark.skipif(not RUN_DAGGER, reason="set ASSAY_DAGGER_INTEGRATION=1")
def test_should_register_every_standing_project_check() -> None:
    # Given / When
    result = _dagger("check", "-l")

    # Then
    assert result.returncode == 0, result.stderr
    assert _check_names(result.stdout) == EXPECTED_CHECKS


@pytest.mark.skipif(not RUN_DAGGER, reason="set ASSAY_DAGGER_INTEGRATION=1")
def test_should_build_verified_release_artifacts(tmp_path: Path) -> None:
    # Given
    destination = tmp_path / "release"

    # When
    result = _dagger("call", "artifacts", "-o", str(destination))

    # Then
    assert result.returncode == 0, result.stderr
    assert (destination / "SHA256SUMS").is_file()
    assert len(tuple((destination / "python").iterdir())) == 2
    assert len(tuple((destination / "npm").iterdir())) == 1


@pytest.mark.skipif(not RUN_DAGGER, reason="set ASSAY_DAGGER_INTEGRATION=1")
def test_should_export_identical_release_bytes_twice(tmp_path: Path) -> None:
    # Given
    first, second = tmp_path / "first", tmp_path / "second"

    # When
    results = (
        _dagger("call", "artifacts", "-o", str(first)),
        _dagger("call", "artifacts", "-o", str(second)),
    )

    # Then
    assert all(result.returncode == 0 for result in results)
    assert _tree_hashes(first) == _tree_hashes(second)
