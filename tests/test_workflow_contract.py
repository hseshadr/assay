from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path
from typing import cast

import pytest
import yaml

from assay.settings import AssaySettings

_WORKFLOW_DIR = Path(".github/workflows")
_WORKFLOW_NAMES = ("ci.yml", "security-audit.yml", "publish.yml")
_ACTION_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
_ACTION_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "astral-sh/setup-uv": "c771a70e6277c0a99b617c7a806ffedaca235ff9",
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "pnpm/action-setup": "0ebf47130e4866e96fce0953f49152a61190b271",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
    "gitleaks/gitleaks-action": "e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e",
    "pypa/gh-action-pypi-publish": "dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
}
_ACTION_VERSIONS = {
    "actions/checkout": "v7.0.1",
    "actions/setup-python": "v7.0.0",
    "astral-sh/setup-uv": "v9.0.0",
    "actions/setup-node": "v7.0.0",
    "pnpm/action-setup": "v6.0.9",
    "actions/upload-artifact": "v4.6.2",
    "actions/download-artifact": "v4.3.0",
    "gitleaks/gitleaks-action": "v3.0.0",
    "pypa/gh-action-pypi-publish": "v1.14.2",
}
_NPM_PUBLISHER_SHA512 = (
    "b885e890b9418fa1693544d05f53e64f9a73ec194837d4258b15fecdd692347b1dd2a517b1b0cbaf"
    "9d31cd8e92c3b70956bd2ecc72833a57b4b3098f5bfa7943"
)


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return cast(dict[str, object], value)


def _workflow(name: str) -> dict[str, object]:
    path = _WORKFLOW_DIR / name
    assert path.is_file(), f"missing standalone workflow: {path}"
    loader = yaml.BaseLoader(path.read_text(encoding="utf-8"))
    try:
        document = loader.get_single_data()
    finally:
        loader.dispose()
    return _mapping(document)


def _jobs(workflow: dict[str, object]) -> dict[str, object]:
    return _mapping(workflow["jobs"])


def _job(workflow: dict[str, object], name: str) -> dict[str, object]:
    return _mapping(_jobs(workflow)[name])


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return [_mapping(step) for step in steps]


def _commands(job: dict[str, object]) -> str:
    return "\n".join(str(step["run"]) for step in _steps(job) if "run" in step)


def _action_uses(workflow: dict[str, object]) -> tuple[str, ...]:
    jobs = (_mapping(value) for value in _jobs(workflow).values())
    return tuple(str(step["uses"]) for job in jobs for step in _steps(job) if "uses" in step)


def _permissions(value: object) -> dict[str, object]:
    return {} if value in (None, "") else _mapping(value)


def _release_fixture(tmp_path: Path, *, npm_version: str) -> Path:
    shutil.copytree("scripts", tmp_path / "scripts")
    shutil.copytree("src/assay", tmp_path / "src/assay")
    (tmp_path / "ts").mkdir()
    package = json.loads(Path("ts/package.json").read_text(encoding="utf-8"))
    package["version"] = npm_version
    (tmp_path / "ts/package.json").write_text(json.dumps(package), encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "assay-tests@example.invalid")
    _git(tmp_path, "config", "user.name", "Assay Tests")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "fixture")
    return tmp_path / "scripts/verify_release_identity.py"


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _run_identity(script: Path, tag: str) -> subprocess.CompletedProcess[str]:
    root = script.parents[1]
    _git(root, "tag", tag)
    sha = _git(root, "rev-parse", "HEAD")
    return subprocess.run(
        ["python", str(script), tag, sha],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def _node_environment() -> dict[str, str]:
    environments = tuple((Path.home() / ".nvm/versions/node").glob("v22.*/bin"))
    if not environments:
        return dict(os.environ)
    selected = max(environments, key=lambda path: tuple(map(int, path.parent.name[1:].split("."))))
    return dict(os.environ) | {"PATH": f"{selected}:{os.environ['PATH']}"}


def _wrong_node_environment(tmp_path: Path) -> dict[str, str]:
    binary = tmp_path / "node"
    binary.write_text('#!/bin/sh\necho "v26.5.0"\n', encoding="utf-8")
    binary.chmod(0o755)
    return dict(os.environ) | {"PATH": f"{tmp_path}:/usr/bin:/bin"}


def _expose_command(tools: Path, command: str, source: dict[str, str]) -> None:
    executable = shutil.which(command, path=source["PATH"])
    assert executable is not None
    target = tools / command
    target.write_text(
        f'#!/bin/sh\nexec {shlex.quote(executable)} "$@"\n',
        encoding="utf-8",
    )
    target.chmod(0o755)


def _without_coreutils_environment(tmp_path: Path) -> dict[str, str]:
    source = _node_environment()
    tools = tmp_path / "tools"
    tools.mkdir()
    for command in ("node", "npm", "pnpm", "uv"):
        _expose_command(tools, command, source)
    return source | {"PATH": f"{tools}:/usr/bin:/bin"}


def _workflow_pnpm_environment(tmp_path: Path) -> dict[str, str]:
    source = _node_environment()
    tools = tmp_path / "workflow-tools"
    tools.mkdir()
    for command in ("node", "npm", "pnpm", "uv"):
        _expose_command(tools, command, source)
    corepack = tools / "corepack"
    corepack.write_text(
        "#!/bin/sh\necho unexpected Corepack invocation >&2\nexit 86\n",
        encoding="utf-8",
    )
    corepack.chmod(0o755)
    return source | {"PATH": f"{tools}:/usr/bin:/bin"}


def _build_release_fixture(tmp_path: Path, *, environment: dict[str, str] | None = None) -> Path:
    root = tmp_path / "release"
    result = subprocess.run(
        ["bash", "scripts/build_release_artifacts.sh", root],
        check=False,
        capture_output=True,
        text=True,
        env=environment or _node_environment(),
    )
    assert result.returncode == 0, result.stderr
    return root


def _expected_digest_lines(root: Path) -> tuple[str, ...]:
    paths = sorted(
        (*root.glob("python/*.whl"), *root.glob("python/*.tar.gz"), *root.glob("npm/*.tgz"))
    )
    return tuple(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}"
        for path in paths
    )


def test_should_define_all_standalone_workflows_as_valid_mappings() -> None:
    # Given the standalone workflow contract
    # When each required workflow is parsed as YAML
    workflows = tuple(_workflow(name) for name in _WORKFLOW_NAMES)
    # Then every workflow has independently executable jobs
    assert all(_jobs(workflow) for workflow in workflows)


def test_should_pin_every_third_party_action_to_an_immutable_commit() -> None:
    # Given every third-party action used by the release system
    uses = tuple(use for name in _WORKFLOW_NAMES for use in _action_uses(_workflow(name)))
    # When action references are checked
    unpinned = tuple(use for use in uses if _ACTION_PIN.fullmatch(use) is None)
    # Then no mutable tag or branch can change the reviewed workflow
    assert uses
    assert unpinned == ()
    assert {
        use.partition("@")[0]: use.partition("@")[2]
        for use in uses
        if use.partition("@")[0] in _ACTION_PINS
    } == _ACTION_PINS


def test_should_bind_every_action_sha_to_its_exact_documented_version() -> None:
    # Given every immutable action reference in every standalone workflow
    source = "\n".join(
        (_WORKFLOW_DIR / name).read_text(encoding="utf-8") for name in _WORKFLOW_NAMES
    )
    pattern = re.compile(r"uses:\s+([^@\s]+)@([0-9a-f]{40})\s+#\s+(v\S+)")
    documented = {name: (sha, version) for name, sha, version in pattern.findall(source)}
    expected = {name: (_ACTION_PINS[name], _ACTION_VERSIONS[name]) for name in _ACTION_PINS}
    # When SHA pins are tied back to reviewed upstream releases
    # Then no bare digest can silently lose its human-auditable version identity
    assert documented == expected
    assert len(pattern.findall(source)) == sum(
        len(_action_uses(_workflow(name))) for name in _WORKFLOW_NAMES
    )


def test_should_isolate_oidc_write_in_the_minimal_publish_job() -> None:
    # Given all workflow and job permissions
    workflows = {name: _workflow(name) for name in _WORKFLOW_NAMES}
    writers: list[tuple[str, str, str]] = []
    for name, workflow in workflows.items():
        for job_name, value in _jobs(workflow).items():
            for scope, access in _permissions(_mapping(value).get("permissions")).items():
                if access == "write":
                    writers.append((name, job_name, scope))
    # Then only the independent registry publishers can mint OIDC identities
    assert writers == [
        ("publish.yml", "publish-python", "id-token"),
        ("publish.yml", "publish-npm", "id-token"),
    ]


def test_should_keep_default_and_build_permissions_least_privileged() -> None:
    # Given each workflow default and the unprivileged release build
    workflows = tuple(_workflow(name) for name in _WORKFLOW_NAMES)
    publish_build = _job(workflows[-1], "build")
    # Then defaults are read-only or empty and build cannot mint credentials
    assert tuple(_permissions(item.get("permissions")) for item in workflows) == (
        {"contents": "read"},
        {"contents": "read"},
        {},
    )
    assert _permissions(publish_build.get("permissions")) == {"contents": "read"}


def test_should_generate_exact_commit_language_parity_and_example_evidence() -> None:
    # Given the standalone CI workflow
    workflow = _workflow("ci.yml")
    jobs = _jobs(workflow)
    commands = "\n".join(_commands(_mapping(job)) for job in jobs.values())
    # Then it covers both runtimes, the shared vectors, mutations, and the real example
    assert set(jobs) == {
        "python",
        "typescript",
        "parity",
        "mutation",
        "example",
        "benchmarks",
        "artifacts",
    }
    assert tuple(_mapping(job)["name"] for job in jobs.values()) == (
        "Python 3.13",
        "TypeScript (Node 22.13.0)",
        "Python/TypeScript parity",
        "Mutation guards",
        "Installed-artifact example",
        "Frozen benchmarks",
        "Release artifacts",
    )
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in commands
    assert "tests/test_consumer_conformance.py" in commands
    assert "src/compositionVectors.test.ts" in commands
    assert "tests/test_example.py" in commands
    assert "tests/test_measurement.py" in commands
    assert "22.13.0" in str(_job(workflow, "typescript"))
    assert all(_mapping(job)["runs-on"] == "ubuntu-24.04" for job in jobs.values())


def test_should_provision_node_and_pnpm_for_the_cross_runtime_python_gate() -> None:
    # Given the Python job runs documentation and artifact contract tests
    steps = _steps(_job(_workflow("ci.yml"), "python"))
    actions = {str(step.get("uses", "")).partition("@")[0]: step for step in steps}
    # Then the hosted job provides the exact cross-runtime tools those tests execute
    assert {"actions/setup-node", "pnpm/action-setup"} <= actions.keys()
    assert _mapping(actions["actions/setup-node"]["with"])["node-version"] == "22.13.0"
    assert _mapping(actions["pnpm/action-setup"]["with"])["version"] == "11.5.0"


def _clean_checkout(destination: Path) -> str:
    ignored = shutil.ignore_patterns(
        ".git", ".venv", "node_modules", "dist", "coverage", ".pytest_cache", "__pycache__"
    )
    shutil.copytree(Path.cwd(), destination, ignore=ignored)
    _git(destination, "init", "-q")
    _git(destination, "config", "user.email", "assay-tests@example.invalid")
    _git(destination, "config", "user.name", "Assay Tests")
    _git(destination, "add", ".")
    _git(destination, "commit", "-qm", "clean checkout")
    return _git(destination, "rev-parse", "HEAD")


def test_should_rehearse_the_installed_measurement_job_from_a_dependency_clean_checkout(
    tmp_path: Path,
) -> None:
    # Given the exact installed-artifact command and a checkout with no managed environments
    checkout = tmp_path / "checkout"
    sha = _clean_checkout(checkout)
    steps = _steps(_job(_workflow("ci.yml"), "example"))
    command = next(
        str(step["run"]) for step in steps if "installed Python/npm example" in str(step)
    )
    assert "uv sync --frozen --all-groups --all-extras" in command
    assert not (checkout / ".venv").exists()
    assert not (checkout / "ts/node_modules").exists()
    # When the hosted command runs with its exact SHA and Node toolchain
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", command],
        cwd=checkout,
        check=False,
        capture_output=True,
        text=True,
        env=_node_environment() | {"GITHUB_SHA": sha},
    )
    # Then optional measurement dependencies were actually provisioned and the job is green
    assert result.returncode == 0, result.stderr
    assert "754" not in result.stdout  # the isolated job runs only its owned evidence


def test_should_build_and_clean_install_every_release_artifact() -> None:
    # Given the CI artifact job and unprivileged release build
    ci_artifacts = _commands(_job(_workflow("ci.yml"), "artifacts"))
    release_build = _commands(_job(_workflow("publish.yml"), "build"))
    # Then CI calls the real builder and tagged releases run the complete local gate
    assert "bash scripts/build_release_artifacts.sh release" in ci_artifacts
    assert "ASSAY_ARTIFACT_ROOT=release uv run poe release-candidate" in release_build


def test_should_verify_real_release_artifacts_through_clean_installs(tmp_path: Path) -> None:
    # Given real wheel, sdist, and npm tarball candidates
    artifacts = _build_release_fixture(tmp_path)
    # When the local artifact verifier inspects and clean-installs them
    result = subprocess.run(
        [
            sys.executable,
            Path("scripts/verify_release_artifacts.py").resolve(),
            artifacts.relative_to(tmp_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=_node_environment(),
    )
    # Then all three consumer surfaces pass with aligned metadata
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "verified release artifacts: assay-engine 0.5.0.dev0 and @edgeproc/assay 0.5.0-dev.0\n"
    )


def test_should_explain_node_22_requirement_before_running_release_gate(tmp_path: Path) -> None:
    # Given a maintainer shell whose active Node is not the release runtime
    environment = _wrong_node_environment(tmp_path)
    # When the local release candidate starts
    result = subprocess.run(
        ["bash", "scripts/verify_release_candidate.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    # Then it stops before installation with one stable actionable message
    assert (result.returncode, result.stdout, result.stderr) == (
        1,
        "",
        "release candidate requires Node 22.13.0; detected v26.5.0\n",
    )


def test_should_generate_sorted_digests_without_gnu_coreutils(tmp_path: Path) -> None:
    # Given a stock-macOS-style PATH with release runtimes but no sha256sum
    environment = _without_coreutils_environment(tmp_path)
    # When the real release builder creates all three artifacts
    artifacts = _build_release_fixture(tmp_path, environment=environment)
    # Then Python generates a correct deterministic manifest without Coreutils
    manifest = (artifacts / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert tuple(manifest) == _expected_digest_lines(artifacts)


def test_should_build_with_workflow_pinned_pnpm_without_invoking_corepack(tmp_path: Path) -> None:
    # Given a hosted-style PATH with pinned pnpm and a conflicting Corepack client
    environment = _workflow_pnpm_environment(tmp_path)
    # When the real release builder creates and clean-installs every package
    artifacts = _build_release_fixture(tmp_path, environment=environment)
    # Then it succeeds through the workflow-pinned pnpm executable
    assert len(tuple((artifacts / "python").glob("*.whl"))) == 1
    assert len(tuple((artifacts / "python").glob("*.tar.gz"))) == 1
    assert len(tuple((artifacts / "npm").glob("*.tgz"))) == 1


def test_should_stage_npm_with_a_present_but_non_gnu_sha512sum(
    tmp_path: Path,
) -> None:
    # Given Darwin-like tools where sha512sum exists but has no GNU check/status flags
    source = _node_environment()
    tools = tmp_path / "tools"
    tools.mkdir()
    for command in ("node", "npm", "python3"):
        _expose_command(tools, command, source)
    shim = tools / "sha512sum"
    shim.write_text("#!/bin/sh\nexit 91\n", encoding="utf-8")
    shim.chmod(0o755)
    destination = tmp_path / "publisher"
    # When the unprivileged staging script verifies the fixed npm archive
    result = subprocess.run(
        ["bash", "scripts/stage_npm_publisher.sh", destination],
        check=False,
        capture_output=True,
        text=True,
        env=source | {"PATH": f"{tools}:/usr/bin:/bin"},
    )
    # Then it uses portable hashlib verification rather than probing command presence
    assert result.returncode == 0, result.stderr
    assert {path.name for path in destination.iterdir()} == {"npm-12.0.2.tgz"}


def test_should_preserve_a_self_relative_hosted_pnpm_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a hosted pnpm shim that locates its module relative to its invoked path
    host = tmp_path / "host"
    module = host / "global/v11/test/node_modules/pnpm/bin/pnpm.mjs"
    module.parent.mkdir(parents=True)
    module.write_text("#!/bin/sh\necho 11.5.0\n", encoding="utf-8")
    module.chmod(0o755)
    binaries = host / "bin"
    binaries.mkdir()
    for command in ("node", "npm", "uv"):
        binary = binaries / command
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)
    pnpm = binaries / "pnpm"
    pnpm.write_text(
        '#!/bin/sh\nexec "$(dirname "$0")/../global/v11/test/'
        'node_modules/pnpm/bin/pnpm.mjs" "$@"\n',
        encoding="utf-8",
    )
    pnpm.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(binaries))
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    # When the restricted test PATH exposes that launcher
    environment = _workflow_pnpm_environment(isolated)
    result = subprocess.run(
        ["pnpm", "--version"], check=False, capture_output=True, text=True, env=environment
    )
    # Then pnpm still resolves its real adjacent module rather than the temporary PATH
    assert (result.returncode, result.stdout) == (0, "11.5.0\n")


def test_should_build_a_small_runtime_only_python_sdist(tmp_path: Path) -> None:
    # Given a release build after the TypeScript dependency and coverage gates
    artifacts = _build_release_fixture(tmp_path)
    sdist = next((artifacts / "python").glob("*.tar.gz"))
    # When the source archive membership is inspected
    with tarfile.open(sdist, "r:gz") as archive:
        paths = tuple(Path(member.name).parts[1:] for member in archive.getmembers())
    roots = {parts[0] for parts in paths if parts}
    # Then only the Python runtime and its packaging metadata are shipped
    assert sdist.stat().st_size < 1_000_000
    assert roots == {"LICENSE", "PKG-INFO", "README.md", "pyproject.toml", "src"}
    assert ("src", "assay", "compose.py") in paths


def test_should_scan_full_history_and_audit_locked_dependencies() -> None:
    # Given the scheduled security workflow
    workflow = _workflow("security-audit.yml")
    commands = "\n".join(_commands(_mapping(job)) for job in _jobs(workflow).values())
    checkout = _steps(_job(workflow, "secrets"))[0]
    assert set(_jobs(workflow)) == {"secrets", "dependencies", "workflows"}
    assert tuple(_mapping(job)["name"] for job in _jobs(workflow).values()) == (
        "Full-history secret scan",
        "Locked dependency audits",
        "Workflow security",
    )
    assert {"push", "pull_request", "schedule"} == set(_mapping(workflow["on"]))
    # Then history, Python lock, npm lock, actionlint, and zizmor are all enforced
    assert _mapping(checkout["with"])["fetch-depth"] == "0"
    assert "gitleaks git --log-opts=--all" in commands
    assert "uv export --frozen --all-groups" in commands
    assert "pnpm --dir ts install --frozen-lockfile --ignore-scripts" in commands
    assert "pnpm --dir ts audit --audit-level high" in commands
    assert "actionlint@v1.7.12" in commands
    assert "zizmor==1.29.0" in commands
    assert "shellcheck" in commands
    assert "pip-audit==2.10.1" in commands
    assert 'GITLEAKS_VERSION: "8.30.1"' in Path(".github/workflows/security-audit.yml").read_text(
        encoding="utf-8"
    )


def test_should_scope_the_historical_public_key_exception_to_one_fingerprint() -> None:
    # Given one confirmed public-key test vector in repository history
    lines = Path(".gitleaksignore").read_text(encoding="utf-8").splitlines()
    # When the Gitleaks exception is reviewed
    entries = tuple(line for line in lines if line and not line.startswith("#"))
    # Then only the exact historical finding is ignored; no path or rule is broad-allowed
    assert entries == ("8e309ff7a0bbeca01c0d283cbe138adbd6641704:ts/README.md:generic-api-key:43",)
    assert lines[0] == "# documented Ed25519 public key test vector; not secret"


def test_should_trigger_publication_only_for_version_tags_without_tokens() -> None:
    # Given the publish workflow event and source
    workflow = _workflow("publish.yml")
    triggers = _mapping(workflow["on"])
    source = (_WORKFLOW_DIR / "publish.yml").read_text(encoding="utf-8")
    # Then only version tags enter eligibility and no token secret is accepted
    push = _mapping(triggers["push"])
    assert push == {"tags": ["v*.*.*"]}
    assert set(triggers) == {"push"}
    assert "verify_release_identity.py" in _commands(_job(workflow, "build"))
    assert re.search(r"secrets\.[A-Za-z0-9_]*TOKEN", source) is None
    assert _mapping(workflow["concurrency"]) == {
        "group": "publish-assay",
        "cancel-in-progress": "false",
    }


def test_should_recheck_digest_metadata_and_registries_after_publish() -> None:
    # Given independent registry lanes and an unprivileged post-publish verifier
    workflow = _workflow("publish.yml")
    python_lane = _commands(_job(workflow, "preflight-python"))
    npm_lane = _commands(_job(workflow, "preflight-npm"))
    registry = _commands(_job(workflow, "verify-published"))
    # Then each lane safely skips only byte-identical existing artifacts
    assert "scripts.registry_release_guard pypi" in python_lane
    assert "scripts.registry_release_guard npm" in npm_lane
    assert "needs.preflight-python.outputs.publish == 'true'" in str(
        _job(workflow, "publish-python")
    )
    assert "needs.preflight-npm.outputs.publish == 'true'" in str(_job(workflow, "publish-npm"))
    preflights = {"preflight-python", "preflight-npm"}
    assert preflights <= set(_job(workflow, "publish-python")["needs"])
    assert preflights <= set(_job(workflow, "publish-npm")["needs"])
    assert {"publish-python", "publish-npm"} <= set(_job(workflow, "verify-published")["needs"])
    assert "scripts/verify_published_release.py" in registry
    assert "release" in registry
    verifier = Path("scripts/verify_published_release.py").read_text(encoding="utf-8")
    assert "materialize_served_bundle" in verifier
    assert "verify_release_artifacts.py" in verifier
    assert "timeout_seconds=600.0" in verifier


def test_should_skip_only_identical_provenanced_registry_artifacts(tmp_path: Path) -> None:
    # Given missing, identical, and mismatched registry states
    sys.path.insert(0, str(Path.cwd()))
    try:
        guard = importlib.import_module("scripts.registry_release_guard")
    finally:
        sys.path.pop(0)
    python = tmp_path / "python"
    python.mkdir()
    files = (python / "assay_engine.whl", python / "assay_engine.tar.gz")
    for index, path in enumerate(files):
        path.write_bytes(f"python-{index}".encode())
    urls = [
        {
            "filename": path.name,
            "digests": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        }
        for path in files
    ]
    npm = tmp_path / "edgeproc-assay.tgz"
    npm.write_bytes(b"npm")
    integrity = base64.b64encode(hashlib.sha512(npm.read_bytes()).digest()).decode()
    npm_payload = {
        "dist": {
            "shasum": hashlib.sha1(npm.read_bytes(), usedforsecurity=False).hexdigest(),
            "integrity": f"sha512-{integrity}",
            "attestations": {
                "url": "https://registry.npmjs.org/-/npm/v1/attestations/example",
                "provenance": {"predicateType": "https://slsa.dev/provenance/v1"},
            },
        }
    }
    # Then missing versions publish, identical provenanced versions skip, and drift fails closed
    assert guard.pypi_release_state(python, None, set()) is True
    assert guard.pypi_release_state(python, {"urls": urls}, {path.name for path in files}) is False
    attestation = {"attestations": [{}]}
    pypi_attestation = {"attestation_bundles": [{}]}
    assert guard.provenance_payload_valid(attestation) is True
    assert guard.provenance_payload_valid(pypi_attestation) is True
    assert guard.npm_release_state(npm, None, None) is True
    assert guard.npm_release_state(npm, npm_payload, attestation) is False
    with pytest.raises(ValueError, match="PyPI artifact or provenance mismatch"):
        guard.pypi_release_state(python, {"urls": urls}, set())
    with pytest.raises(ValueError, match="npm artifact or provenance mismatch"):
        guard.npm_release_state(npm, {"dist": {}}, None)
    untrusted = json.loads(json.dumps(npm_payload))
    untrusted["dist"]["attestations"]["url"] = "https://example.invalid/attestations"
    with pytest.raises(ValueError, match="npm artifact or provenance mismatch"):
        guard.npm_release_state(npm, untrusted, attestation)


def test_should_run_python_benchmark_in_the_complete_release_gate() -> None:
    # Given the local gate used unchanged by the hosted release build
    commands = Path("scripts/verify_release_candidate.sh").read_text(encoding="utf-8")
    # Then Python performance evidence cannot disappear from a release candidate
    assert "uv run python -m benchmarks.release" in commands


def test_should_pin_and_record_every_local_release_tool() -> None:
    # Given the local gate is the release build's executable truth
    source = Path("scripts/verify_release_candidate.sh").read_text(encoding="utf-8")
    # Then ambient developer tools cannot silently differ from hosted release tools
    for expected in ("3.13", "uv 0.11.32", "1.7.12", "8.30.1"):
        assert expected in source
    assert "shellcheck --version" in source


def test_should_bound_the_hosted_benchmark_job_and_typescript_children() -> None:
    # Given heavy performance evidence executes in hosted CI and isolated Node children
    job = _job(_workflow("ci.yml"), "benchmarks")
    source = Path("ts/benchmarks/release.mjs").read_text(encoding="utf-8")
    # Then hung work is killed above the frozen per-workload budgets
    assert job["timeout-minutes"] == "15"
    assert "timeout:" in source
    assert "benchmark child timed out" in source


def test_should_pin_supported_npm_only_in_the_npm_publish_lane() -> None:
    # Given npm trusted publishing requires a known OIDC-capable client
    workflow = _workflow("publish.yml")
    source = (_WORKFLOW_DIR / "publish.yml").read_text(encoding="utf-8")
    npm_lane = _commands(_job(workflow, "publish-npm"))
    # Then the exact staged client is checksum-verified and confined to that lane
    assert "publish-tools/npm-12.0.2.tgz" in npm_lane
    assert _NPM_PUBLISHER_SHA512 in npm_lane
    assert "SHA512SUMS" not in npm_lane
    assert "sha512sum --check" in npm_lane
    assert "package/bin/npm-cli.js --version" in npm_lane
    assert "package/bin/npm-cli.js publish" in npm_lane
    assert "npm install" not in npm_lane
    assert source.count('node-version: "24.15.0"') == 1


def test_should_pin_python_313_in_every_registry_observer() -> None:
    # Given both preflights and final downloaded-byte verification execute Python tooling
    workflow = _workflow("publish.yml")
    for name in ("preflight-python", "preflight-npm", "verify-published"):
        actions = {
            str(step.get("uses", "")).partition("@")[0]: step
            for step in _steps(_job(workflow, name))
        }
        assert "actions/setup-python" in actions
        assert _mapping(actions["actions/setup-python"]["with"])["python-version"] == "3.13"


def test_should_make_the_privileged_channel_recheck_authoritative_and_fail_closed() -> None:
    # Given the only package publisher rechecks canonical and selected tags immediately
    command = _commands(_job(_workflow("publish.yml"), "publish-npm"))
    # Then only HTTP/package-key absence maps to the explicit marker; malformed state is an error
    assert "__ABSENT__" in command
    assert "has($tag)" in command
    assert 'type != "object"' in command
    assert '.name == "@edgeproc/assay"' in command
    assert '// ""' not in command
    assert "EXPECTED_CHANNEL_VERSION" in command
    assert "EXPECTED_PUBLISH_TAG_VERSION" in command
    assert "--max-filesize 1048576" in command


def test_should_bound_final_polling_and_avoid_shell_dist_tag_fallbacks() -> None:
    # Given the final registry verifier
    command = _commands(_job(_workflow("publish.yml"), "verify-published"))
    source = Path("scripts/verify_published_release.py").read_text(encoding="utf-8")
    # Then one monotonic 600-second budget includes HTTP and only explicit absence is retried
    assert "scripts/verify_published_release.py" in command
    assert "npm view" not in command
    assert "seq 1 60" not in command
    assert "sleep 10" not in command
    assert "time.monotonic" in source
    assert "PropagationPending" in source


def test_should_rebuild_uploadable_artifacts_after_the_clean_local_gate() -> None:
    # Given the local gate removes every ignored release output on exit
    commands = _commands(_job(_workflow("publish.yml"), "build"))
    # Then the unprivileged build recreates the reviewed envelope before upload
    gate = commands.index("ASSAY_ARTIFACT_ROOT=release uv run poe release-candidate")
    rebuild = commands.index("bash scripts/build_release_artifacts.sh release")
    stage = commands.index("bash scripts/stage_npm_publisher.sh publish-tools")
    assert gate < rebuild < stage


def test_should_always_clean_and_prove_the_publish_build_tree() -> None:
    # Given the build lane recreates ignored release and publisher artifacts after the local gate
    build = _job(_workflow("publish.yml"), "build")
    steps = _steps(build)
    cleanup = steps[-1]
    # Then an unconditional final step removes both outputs and proves source-tree cleanliness
    assert cleanup.get("name") == "Always clean release outputs and verify tree"
    assert cleanup.get("if") == "${{ always() }}"
    command = str(cleanup.get("run", ""))
    assert "rm -rf -- release publish-tools" in command
    assert "pnpm --dir ts clean" in command
    assert "test ! -e release" in command
    assert "test ! -e publish-tools" in command
    assert "test ! -e ts/dist" in command
    assert "git diff --exit-code" in command
    assert "git status --porcelain=v1 --untracked-files=all" in command


def test_should_remove_every_ignored_publish_build_output(tmp_path: Path) -> None:
    # Given every ignored output recreated by the publish build after its local gate
    checkout = tmp_path / "checkout"
    _clean_checkout(checkout)
    outputs = (checkout / "release", checkout / "publish-tools", checkout / "ts/dist")
    for output in outputs:
        output.mkdir(parents=True)
        (output / "generated.txt").write_text("generated\n", encoding="utf-8")
    cleanup = _steps(_job(_workflow("publish.yml"), "build"))[-1]
    # When the workflow's unconditional final cleanup runs
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", str(cleanup["run"])],
        cwd=checkout,
        check=False,
        capture_output=True,
        text=True,
        env=_node_environment(),
    )
    # Then no release, publisher, or TypeScript build output survives
    assert result.returncode == 0, result.stderr
    assert all(not output.exists() for output in outputs)


def test_should_keep_npm_prereleases_off_the_latest_channel() -> None:
    # Given stable and prerelease versions accepted by the release workflow
    sys.path.insert(0, str(Path.cwd()))
    try:
        guard = importlib.import_module("scripts.registry_release_guard")
    finally:
        sys.path.pop(0)
    workflow = _workflow("publish.yml")
    preflight = _job(workflow, "preflight-npm")
    publish = _job(workflow, "publish-npm")
    command = _commands(publish)
    # Then only stable releases select latest and every prerelease selects next
    assert guard.npm_dist_tag("0.5.0") == "latest"
    assert guard.npm_dist_tag("0.5.0-dev.0") == "next"
    assert _mapping(preflight["outputs"])["dist-tag"] == "${{ steps.registry.outputs.dist-tag }}"
    assert _mapping(preflight["outputs"])["publish-tag"] == (
        "${{ steps.registry.outputs.publish-tag }}"
    )
    assert '--tag "$NPM_PUBLISH_TAG"' in command
    assert "needs.preflight-npm.outputs.dist-tag" in str(publish)
    assert "needs.preflight-npm.outputs.publish-tag" in str(publish)
    assert "EXPECTED_CHANNEL_VERSION" in command
    assert command.index("registry.npmjs.org/%40edgeproc%2Fassay") < command.index(
        "package/bin/npm-cli.js publish"
    )
    registry = _commands(_job(workflow, "verify-published"))
    assert "scripts/verify_published_release.py" in registry
    assert "npm view" not in registry


def test_should_provision_exact_clean_install_tools_for_final_registry_bytes() -> None:
    # Given final verification clean-installs the bytes downloaded from both registries
    steps = _steps(_job(_workflow("publish.yml"), "verify-published"))
    actions = {str(step.get("uses", "")).partition("@")[0]: step for step in steps}
    # Then no ambient Python, uv, Node, or pnpm runtime can influence that evidence
    assert _mapping(actions["actions/setup-python"]["with"])["python-version"] == "3.13"
    assert _mapping(actions["astral-sh/setup-uv"]["with"])["version"] == "0.11.32"
    assert _mapping(actions["actions/setup-node"]["with"])["node-version"] == "22.13.0"
    assert _mapping(actions["pnpm/action-setup"]["with"])["version"] == "11.5.0"


def test_should_document_the_single_internal_npm_publisher_invariant() -> None:
    # Given package-wide workflow concurrency serializes this repository's releases
    workflow = _workflow("publish.yml")
    operations = Path("docs/OPERATIONS.md").read_text(encoding="utf-8")
    # Then docs do not overclaim protection against external registry writers
    assert _mapping(workflow["concurrency"]) == {
        "group": "publish-assay",
        "cancel-in-progress": "false",
    }
    assert "only Assay publisher invariant" in operations
    assert "external publisher" in operations
    assert "fails closed" in operations


def test_should_name_only_the_unpublished_candidate_versions_in_security_docs() -> None:
    # Given the security model describes registry identities under review
    source = Path("SECURITY.md").read_text(encoding="utf-8")
    # Then it cannot imply that stable 0.5.0 is already the candidate
    assert "0.5.0.dev0" in source
    assert "0.5.0-dev.0" in source
    assert "future 0.5.0" in source


def test_should_skip_the_entire_oidc_job_for_identical_registry_releases() -> None:
    # Given both minimal OIDC jobs and their unprivileged final verifier
    workflow = _workflow("publish.yml")
    python = _job(workflow, "publish-python")
    npm = _job(workflow, "publish-npm")
    verifier = _job(workflow, "verify-published")
    # Then no OIDC-capable runner starts for an already-complete registry lane
    assert python["if"] == "${{ needs.preflight-python.outputs.publish == 'true' }}"
    assert npm["if"] == "${{ needs.preflight-npm.outputs.publish == 'true' }}"
    assert all("if" not in step for step in _steps(python))
    assert all("if" not in step for step in _steps(npm))
    # And the final unprivileged verifier accepts only successful or safely skipped lanes
    assert set(verifier["needs"]) == {
        "preflight-python",
        "preflight-npm",
        "publish-python",
        "publish-npm",
    }
    condition = str(verifier["if"])
    assert "always()" in condition
    assert "!cancelled()" in condition
    assert condition.count("result == 'success'") == 4
    assert condition.count("result == 'skipped'") == 2


def test_should_fail_closed_until_python_and_npm_versions_align(tmp_path: Path) -> None:
    # Given the current intentionally divergent unpublished package versions
    script = _release_fixture(tmp_path / "divergent", npm_version="0.4.1")
    # When a tag matches only the Python candidate
    result = _run_identity(script, "v0.5.0-dev.0")
    # Then release eligibility fails without disclosing artifact metadata
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == "release tag and artifact versions do not match\n"


def test_should_accept_only_one_tag_matching_both_artifact_versions(tmp_path: Path) -> None:
    # Given aligned Python and npm artifact metadata
    script = _release_fixture(tmp_path / "aligned", npm_version="0.5.0-dev.0")
    # When the exact shared version tag is checked
    exact = _run_identity(script, "v0.5.0-dev.0")
    wrong = _run_identity(script, "v0.5.0")
    # Then only the exact tag is release-eligible
    assert (exact.returncode, exact.stdout, exact.stderr) == (
        0,
        "verified release identity: v0.5.0-dev.0\n",
        "",
    )
    assert wrong.returncode == 1


def test_should_expose_runnable_local_security_and_release_equivalents() -> None:
    # Given the project task runner configuration
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    tasks = project["tool"]["poe"]["tasks"]
    # Then local commands cover every hosted security and release gate
    assert {
        "audit",
        "artifacts",
        "secrets",
        "workflow-contract",
        "workflow-lint",
        "workflow-security",
        "release-candidate",
    } <= tasks.keys()


def test_should_document_exact_runtime_settings_without_implying_dotenv_loading() -> None:
    # Given the checked-in shell environment example and the runtime settings model
    source = Path(".env.example").read_text(encoding="utf-8")
    assignments = {
        line.partition("=")[0]: line.partition("=")[2].partition("#")[0].strip()
        for line in source.splitlines()
        if line.startswith("ASSAY_")
    }
    expected = {
        f"ASSAY_{name.upper()}": str(field.default)
        for name, field in AssaySettings.model_fields.items()
    }
    # Then the six live fields/defaults are exact and loading is explicitly caller-owned
    assert assignments == expected
    assert "does not auto-load" in source
    assert "set -a; . ./.env; set +a" in source


def test_should_keep_only_generic_secret_patterns_and_no_audit_export() -> None:
    # Given the repository ignore contract
    entries = {
        line.strip()
        for line in Path(".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    # Then generic key material stays ignored without obsolete product-specific paths
    assert {"*.key", "*.pem"} <= entries
    assert {"private.key", "signing.key", "keys/", "requirements-audit.txt"}.isdisjoint(entries)


def test_should_cool_all_dependency_ecosystems_for_seven_days() -> None:
    # Given each automated dependency-update ecosystem
    document = yaml.safe_load(Path(".github/dependabot.yml").read_text(encoding="utf-8"))
    updates = document["updates"]
    # Then no newly published dependency enters an update PR during the quarantine window
    assert {item["package-ecosystem"] for item in updates} == {
        "github-actions",
        "npm",
        "pip",
    }
    assert all(item["cooldown"] == {"default-days": 7} for item in updates)
