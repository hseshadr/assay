"""Behavioral contracts for Assay's typed Dagger release graph."""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from typing import cast

import dagger
import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / ".dagger/src"))

from assay_dagger.main import Assay  # noqa: E402


class RecordingWorkspace:
    """Record the explicit source root selected by the constructor."""

    def __init__(self) -> None:
        self.path = ""
        self.excludes: list[str] = []

    def directory(self, path: str, *, exclude: list[str]) -> dagger.Directory:
        self.path = path
        self.excludes = exclude
        return cast(dagger.Directory, object())


class CandidateFile:
    """Return one controlled candidate file payload."""

    def __init__(self, contents: str) -> None:
        self._contents = contents

    async def contents(self) -> str:
        return self._contents


class RecordingCandidate:
    """Expose a controlled candidate directory without a Dagger engine."""

    def __init__(self, entries: list[str], files: dict[str, str], prefix: str = "") -> None:
        self._entries = entries
        self._files = files
        self._prefix = prefix

    async def entries(self) -> list[str]:
        prefix = f"{self._prefix}/" if self._prefix else ""
        children = {
            entry.removeprefix(prefix).split("/", maxsplit=1)[0]
            for entry in self._entries
            if entry.startswith(prefix)
        }
        return sorted(children)

    def directory(self, path: str) -> dagger.Directory:
        prefix = f"{self._prefix}/{path}" if self._prefix else path
        return cast(dagger.Directory, RecordingCandidate(self._entries, self._files, prefix))

    def file(self, path: str) -> dagger.File:
        return cast(dagger.File, CandidateFile(self._files[path]))


def test_should_construct_from_one_explicit_typed_workspace() -> None:
    # Given
    workspace = RecordingWorkspace()

    # When
    Assay.create(cast(dagger.Workspace, workspace))

    # Then
    assert workspace.path == "/"
    assert ".git" in workspace.excludes
    assert "**/node_modules" in workspace.excludes
    assert {".env", "**/.env", "*.key", "**/*.key", "*.pem", "**/*.pem"} <= set(workspace.excludes)
    signature = inspect.signature(Assay.create, eval_str=True)
    assert signature.parameters["workspace"].annotation is dagger.Workspace


def test_should_expose_one_complete_ci_and_release_graph() -> None:
    # Given
    expected = {
        "artifacts",
        "ci",
        "python",
        "typescript",
        "security",
        "release_candidate",
        "pypi_required",
        "publish_npm",
    }

    # When
    available = {name for name in expected if hasattr(Assay, name)}

    # Then
    assert available == expected


def test_should_type_every_authority_and_artifact_boundary() -> None:
    # Given / When
    candidate = inspect.signature(Assay.release_candidate, eval_str=True)
    npm = inspect.signature(Assay.publish_npm, eval_str=True)

    # Then
    assert candidate.parameters["github_token"].annotation is dagger.Secret
    assert candidate.return_annotation is dagger.Directory
    assert npm.parameters["candidate"].annotation is dagger.Directory
    assert npm.parameters["oidc_url"].annotation is dagger.Secret
    assert npm.parameters["oidc_token"].annotation is dagger.Secret
    assert npm.return_annotation is str


def test_should_keep_quality_on_the_typed_source_but_overlay_only_git_history() -> None:
    # Given / When
    implementation = inspect.getsource(Assay._source_with_history)

    # Then
    assert 'filter(include=[".git", ".git/**"])' in implementation
    assert 'git_metadata.with_directory("/", source)' in implementation
    assert 'history.with_directory("/", source)' not in implementation


def test_should_run_both_dependency_audits_and_both_secret_scans() -> None:
    # Given / When
    security = inspect.getsource(Assay._security)
    secrets = inspect.getsource(Assay._secret_scan)
    module = inspect.getmodule(Assay)

    # Then
    assert module is not None
    assert "GITLEAKS_SNAPSHOT" in secrets
    assert "GITLEAKS_HISTORY" in secrets
    assert "audit-python" in security
    assert "audit-typescript" in security


def test_should_build_candidate_from_exact_history_and_record_registry_decisions() -> None:
    # Given / When
    release = inspect.getsource(Assay.release_candidate)
    candidate = inspect.getsource(Assay._candidate)
    artifacts = inspect.getsource(Assay._artifact_container)

    # Then
    assert "_source_with_history" in release
    assert "_hosted" in release
    assert "_registry_preflight" in candidate
    assert "build_release_artifacts.sh" in artifacts
    assert "stage_npm_publisher.sh" in candidate
    assert "CANDIDATE-SHA256SUMS" in candidate


def test_should_accept_only_a_checksum_bound_candidate_plan() -> None:
    # Given
    sha = "a" * 40
    entries = ["CANDIDATE-SHA256SUMS", "publication/pypi.env"]
    files = {
        "publication/pypi.env": f"expected-sha={sha}\npublish=true\n",
        "CANDIDATE-SHA256SUMS": "",
    }
    candidate = RecordingCandidate(entries, files)

    # When
    required = asyncio.run(
        Assay._pypi_decision(cast(dagger.Directory, candidate), expected_sha=sha)
    )

    # Then
    assert required is True


def test_should_reject_a_candidate_plan_for_another_commit() -> None:
    # Given
    candidate = RecordingCandidate(
        ["publication/pypi.env"],
        {"publication/pypi.env": f"expected-sha={'a' * 40}\npublish=true\n"},
    )

    # When / Then
    with pytest.raises(ValueError, match="candidate commit identity differs"):
        asyncio.run(Assay._pypi_decision(cast(dagger.Directory, candidate), expected_sha="b" * 40))


def test_should_reject_a_non_boolean_npm_publish_decision() -> None:
    # Given
    sha = "a" * 40
    plan = (
        f"expected-sha={sha}\npublish=maybe\ndist-tag=latest\npublish-tag=latest\n"
        "channel-version=__ABSENT__\npublish-tag-version=__ABSENT__\n"
    )
    candidate = RecordingCandidate(["publication/npm.env"], {"publication/npm.env": plan})

    # When / Then
    with pytest.raises(ValueError, match="candidate npm decision is malformed"):
        asyncio.run(Assay._npm_decision(cast(dagger.Directory, candidate), expected_sha=sha))


def test_should_reject_extra_material_inside_the_release_envelope() -> None:
    # Given
    entries = [
        "CANDIDATE-SHA256SUMS",
        "publication/npm.env",
        "publication/pypi.env",
        "publish-tools/npm-12.0.2.tgz",
        "release/SHA256SUMS",
        "release/npm/edgeproc-assay-0.5.0-dev.3.tgz",
        "release/python/assay_engine-0.5.0.dev3-py3-none-any.whl",
        "release/python/assay_engine-0.5.0.dev3.tar.gz",
        "release/source.py",
    ]
    candidate = RecordingCandidate(entries, {})

    # When / Then
    with pytest.raises(ValueError, match="candidate release envelope differs"):
        asyncio.run(Assay._require_candidate_shape(cast(dagger.Directory, candidate)))


def test_should_pin_every_downloaded_tool_and_package_manager() -> None:
    # Given / When
    module = inspect.getmodule(Assay)

    # Then
    assert module is not None
    assert "@sha256:" in module.PYTHON_IMAGE
    assert "@sha256:" in module.NODE_IMAGE
    assert "@sha256:" in module.UV_IMAGE
    assert "@sha256:" in module.GITLEAKS_IMAGE
    assert "@sha256:" in module.ACTIONLINT_IMAGE
    assert module.PNPM_VERSION == "11.5.0"


def test_should_lock_temporal_audit_tools_in_the_repository_environment() -> None:
    # Given / When
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    # Then scheduled audits cannot resolve an unreviewed uvx environment at runtime
    assert '"pip-audit==2.10.1"' in project
    assert '"zizmor==1.29.0"' in project
    assert "uvx --from pip-audit" not in project
    assert "uvx zizmor" not in project
    assert 'name = "pip-audit"' in lock
    assert 'name = "zizmor"' in lock


def test_should_install_both_locked_uv_executables() -> None:
    # Given / When
    toolchain = inspect.getsource(Assay._toolchain)

    # Then dependency-audit tasks can invoke the uvx binary from the same pinned image
    assert '.file("/uv")' in toolchain
    assert '.file("/uvx")' in toolchain
    assert 'with_file("/usr/local/bin/uvx", uvx)' in toolchain


def test_should_reduce_the_total_dagger_and_workflow_surface() -> None:
    # Given
    paths = (
        *tuple((ROOT / ".dagger/src/assay_dagger").glob("*.py")),
        *tuple((ROOT / ".github/workflows").glob("*.yml")),
    )

    # When
    lines = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in paths)

    # Then
    assert 400 <= lines <= 700
