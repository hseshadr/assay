from __future__ import annotations

import base64
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest


def _identity_fixture(tmp_path: Path, *, python_version: str, npm_version: str) -> Path:
    root = tmp_path / f"identity-{python_version}-{npm_version}"
    shutil.copytree("scripts", root / "scripts")
    shutil.copytree("src/assay", root / "src/assay")
    source = root / "src/assay/_version.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace("0.5.0.dev0", python_version),
        encoding="utf-8",
    )
    (root / "ts").mkdir()
    package = json.loads(Path("ts/package.json").read_text(encoding="utf-8"))
    package["version"] = npm_version
    (root / "ts/package.json").write_text(json.dumps(package), encoding="utf-8")
    return root / "scripts/verify_release_identity.py"


def _run_identity(script: Path, tag: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, tag],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("python_version", "npm_version", "tag"),
    [("1.2.3", "1.2.3", "v1.2.3"), ("1.2.3.dev4", "1.2.3-dev.4", "v1.2.3-dev.4")],
)
def test_should_accept_exact_stable_and_dev_release_identities(
    tmp_path: Path, python_version: str, npm_version: str, tag: str
) -> None:
    # Given aligned source identities in the only supported spellings
    script = _identity_fixture(tmp_path, python_version=python_version, npm_version=npm_version)
    # When the exact tag is checked
    result = _run_identity(script, tag)
    # Then release eligibility succeeds without normalization ambiguity
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        f"verified release identity: {tag}\n",
        "",
    )


@pytest.mark.parametrize(
    ("python_version", "npm_version", "tag"),
    [
        ("01.2.3", "01.2.3", "v01.2.3"),
        ("1.02.3", "1.02.3", "v1.02.3"),
        ("1.2.03", "1.2.03", "v1.2.03"),
        ("1.2.3.post1", "1.2.3-post.1", "v1.2.3-post.1"),
        ("1.2.3+local", "1.2.3+local", "v1.2.3+local"),
        ("1.2.3a1", "1.2.3-alpha.1", "v1.2.3-alpha.1"),
        ("1.2.3b1", "1.2.3-beta.1", "v1.2.3-beta.1"),
        ("1.2.3rc1", "1.2.3-rc.1", "v1.2.3-rc.1"),
        ("1.2.3.dev1", "1.2.3-dev1", "v1.2.3-dev1"),
        ("1.2.3.dev1", "1.2.3-dev.2", "v1.2.3-dev.2"),
    ],
)
def test_should_reject_unsupported_or_divergent_release_identities(
    tmp_path: Path, python_version: str, npm_version: str, tag: str
) -> None:
    # Given malformed, unsupported, or divergent source identities
    script = _identity_fixture(tmp_path, python_version=python_version, npm_version=npm_version)
    # When release eligibility is checked
    result = _run_identity(script, tag)
    # Then it fails closed through one value-free message
    assert (result.returncode, result.stdout, result.stderr) == (
        1,
        "",
        "release tag and artifact versions do not match\n",
    )


def _load_guard() -> object:
    sys.path.insert(0, str(Path.cwd()))
    try:
        return importlib.import_module("scripts.registry_release_guard")
    finally:
        sys.path.pop(0)


def _npm_metadata(path: Path) -> dict[str, object]:
    sha1 = hashlib.sha1(path.read_bytes(), usedforsecurity=False).hexdigest()
    sha512 = base64.b64encode(hashlib.sha512(path.read_bytes()).digest()).decode()
    return {
        "dist": {
            "shasum": sha1,
            "integrity": f"sha512-{sha512}",
            "attestations": {
                "url": "https://registry.npmjs.org/-/npm/v1/attestations/example",
                "provenance": {"predicateType": "https://slsa.dev/provenance/v1"},
            },
        }
    }


def _npm_attestation(*, tag: str, sha: str, subject_sha512: str) -> dict[str, object]:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [
            {
                "name": "pkg:npm/%40edgeproc/assay@0.5.0-dev.0",
                "digest": {"sha512": subject_sha512},
            }
        ],
        "predicate": {
            "buildDefinition": {
                "externalParameters": {
                    "workflow": {
                        "repository": "https://github.com/hseshadr/assay",
                        "path": ".github/workflows/publish.yml",
                        "ref": f"refs/tags/{tag}",
                    }
                },
                "resolvedDependencies": [
                    {
                        "uri": f"git+https://github.com/hseshadr/assay@refs/tags/{tag}",
                        "digest": {"gitCommit": sha},
                    }
                ],
            }
        },
    }
    payload = base64.b64encode(json.dumps(statement).encode()).decode()
    return {"attestations": [{"bundle": {"dsseEnvelope": {"payload": payload}}}]}


def _pypi_attestation(
    *, filename: str, sha256: str, repository: str = "hseshadr/assay"
) -> dict[str, object]:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": filename, "digest": {"sha256": sha256}}],
        "predicateType": "https://docs.pypi.org/attestations/publish/v1",
        "predicate": None,
    }
    encoded = base64.b64encode(json.dumps(statement).encode()).decode()
    return {
        "attestation_bundles": [
            {
                "publisher": {
                    "kind": "GitHub",
                    "repository": repository,
                    "workflow": "publish.yml",
                },
                "attestations": [{"envelope": {"statement": encoded}}],
            }
        ]
    }


def test_should_bind_pypi_provenance_to_filename_digest_and_publisher() -> None:
    # Given a PEP 740 provenance bundle from the configured trusted publisher
    guard = _load_guard()
    filename = "assay_engine-0.5.0.dev0-py3-none-any.whl"
    payload = _pypi_attestation(filename=filename, sha256="a" * 64)
    # When the local file identity is checked
    # Then filename, digest, repository, workflow, and publish predicate must all agree
    assert guard.pypi_provenance_valid(payload, filename, "a" * 64) is True
    assert guard.pypi_provenance_valid(payload, filename, "b" * 64) is False
    wrong = _pypi_attestation(filename=filename, sha256="a" * 64, repository="elsewhere/assay")
    assert guard.pypi_provenance_valid(wrong, filename, "a" * 64) is False


def test_should_bind_npm_provenance_to_repository_workflow_tag_and_sha(tmp_path: Path) -> None:
    # Given exact local bytes and an official-shaped npm provenance statement
    guard = _load_guard()
    tarball = tmp_path / "edgeproc-assay.tgz"
    tarball.write_bytes(b"assay-npm")
    metadata = _npm_metadata(tarball)
    sha = "a" * 40
    subject_sha512 = hashlib.sha512(tarball.read_bytes()).hexdigest()
    attestation = _npm_attestation(tag="v0.5.0-dev.0", sha=sha, subject_sha512=subject_sha512)
    identity = guard.ProvenanceIdentity("v0.5.0-dev.0", sha, subject_sha512)
    # When every release binding agrees
    publish = guard.npm_release_state(tarball, metadata, attestation, identity)
    # Then an existing release is safely skipped
    assert publish is False


@pytest.mark.parametrize(("tag", "sha"), [("v0.5.0", "a" * 40), ("v0.5.0-dev.0", "b" * 40)])
def test_should_reject_npm_provenance_bound_to_another_run(
    tmp_path: Path, tag: str, sha: str
) -> None:
    # Given exact bytes but provenance for another tag or commit
    guard = _load_guard()
    tarball = tmp_path / "edgeproc-assay.tgz"
    tarball.write_bytes(b"assay-npm")
    subject_sha512 = hashlib.sha512(tarball.read_bytes()).hexdigest()
    attestation = _npm_attestation(tag=tag, sha=sha, subject_sha512=subject_sha512)
    expected = guard.ProvenanceIdentity("v0.5.0-dev.0", "a" * 40, subject_sha512)
    # When registry state is checked
    # Then the mismatch cannot be treated as a retry-safe skip
    with pytest.raises(ValueError, match="npm artifact or provenance mismatch"):
        guard.npm_release_state(tarball, _npm_metadata(tarball), attestation, expected)


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("0.5.0", None, "latest"),
        ("0.5.0", "0.4.1", "latest"),
        ("0.5.0-dev.0", None, "next"),
        ("0.5.0-dev.1", "0.5.0-dev.0", "next"),
    ],
)
def test_should_allow_only_monotonic_dist_tag_updates(
    candidate: str, current: str | None, expected: str
) -> None:
    # Given a missing or older version on the candidate channel
    guard = _load_guard()
    # When the publish tag is selected
    # Then the release remains on the correct monotonic channel
    assert guard.checked_npm_dist_tag(candidate, current) == expected


@pytest.mark.parametrize(
    ("candidate", "current"),
    [("0.4.1", "0.5.0"), ("0.5.0-dev.0", "0.5.0-dev.1")],
)
def test_should_refuse_a_historical_retry_that_moves_a_dist_tag_backward(
    candidate: str, current: str
) -> None:
    # Given a dist-tag already pointing at a newer version
    guard = _load_guard()
    # When a historical missing release is retried
    # Then the channel cannot be moved backward
    with pytest.raises(ValueError, match="dist-tag would move backward"):
        guard.checked_npm_dist_tag(candidate, current)


@pytest.mark.parametrize(
    ("target", "current"),
    [("0.4.1", "0.5.0"), ("0.5.0-dev.0", "0.5.0-dev.1")],
)
def test_should_accept_a_completed_historical_retry_without_retagging(
    target: str, current: str
) -> None:
    # Given exact target bytes already exist while the channel has advanced
    guard = _load_guard()
    # When final verification checks the untouched channel
    # Then exact or newer same-channel pointers are valid without rollback
    assert guard.dist_tag_is_current_or_newer(target, current) is True


@pytest.mark.parametrize(
    ("version", "tags", "expected"),
    [
        ("1.2.3", {}, "latest"),
        ("1.2.3", {"latest": "1.2.2"}, "latest"),
        ("1.2.3", {"latest": "1.2.4"}, "assay-v1-2-3"),
        ("1.2.3-dev.4", {"next": "1.2.3-dev.5"}, "assay-v1-2-3-dev-4"),
    ],
)
def test_should_select_a_nondefault_tag_for_out_of_order_publication(
    version: str, tags: dict[str, object], expected: str
) -> None:
    # Given absent target bytes and the authoritative package-wide tag state
    guard = _load_guard()
    # When the publish tag is selected immediately before publication
    # Then only a forward release can change latest/next
    assert guard.npm_publish_tag(version, tags) == expected


def test_should_reject_a_version_specific_tag_collision() -> None:
    # Given an out-of-order release whose deterministic nondefault tag is occupied
    guard = _load_guard()
    tags = {"latest": "1.2.4", "assay-v1-2-3": "9.9.9"}
    # When publication is planned
    # Then registry drift fails closed rather than overwriting another tag
    with pytest.raises(ValueError, match="version-specific dist-tag collision"):
        guard.npm_publish_tag("1.2.3", tags)


def test_should_fail_closed_on_cross_channel_registry_state() -> None:
    # Given an externally corrupted canonical tag pointing at another release channel
    guard = _load_guard()
    # When a publish decision is selected
    # Then it cannot be treated as a same-channel semver comparison
    with pytest.raises(ValueError, match="npm channel contains an incompatible version"):
        guard.npm_publish_tag("1.2.3", {"latest": "1.2.4-dev.0"})


def test_should_treat_only_authoritative_404_as_registry_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given registry reads returning authoritative absence or transient failure
    guard = _load_guard()
    missing = urllib.error.HTTPError("https://registry.example/x", 404, "", {}, None)
    unavailable = urllib.error.HTTPError("https://registry.example/x", 503, "", {}, None)
    monkeypatch.setattr(guard.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(guard, "_read_json", lambda _url, _timeout: (_ for _ in ()).throw(missing))
    # Then 404 alone is absence
    assert guard._fetch_json("https://registry.example/x") is None
    monkeypatch.setattr(
        guard, "_read_json", lambda _url, _timeout: (_ for _ in ()).throw(unavailable)
    )
    # And 5xx remains a closed failure after bounded retries
    with pytest.raises(urllib.error.HTTPError) as raised:
        guard._fetch_json("https://registry.example/x")
    assert raised.value.code == 503


def test_should_define_one_exact_mutation_set_across_both_runtimes() -> None:
    # Given the release mutation harness
    sys.path.insert(0, str(Path.cwd() / "scripts"))
    try:
        harness = importlib.import_module("mutation_harness")
    finally:
        sys.path.pop(0)
    # When its active IDs and runners are inspected
    names = tuple(mutation.name for mutation in harness.MUTATIONS)
    runners = {mutation.runner for mutation in harness.MUTATIONS}
    # Then the set is non-vacuous, unique, scoring-only, and cross-runtime
    assert len(names) == 120
    assert len(names) == len(set(names))
    assert runners == {"pytest", "vitest"}
    assert sum(mutation.runner == "vitest" for mutation in harness.MUTATIONS) == 31
    assert "npm-release-quarantine-is-24h" in names
    assert all("envelope" not in name and "ledger" not in name for name in names)
    assert all(not mutation.target.startswith("src/avow/") for mutation in harness.MUTATIONS)
    source = Path("scripts/mutation_harness.py").read_text(encoding="utf-8")
    assert all(token in source for token in ("v22.13.0", "11.5.0", "_tree_snapshot"))


def test_should_reproduce_python_artifacts_across_independent_builds(tmp_path: Path) -> None:
    # Given two clean output directories and the locked no-isolation builder
    first, second = tmp_path / "first", tmp_path / "second"
    # When wheel and sdist candidates are built independently
    for destination in (first, second):
        subprocess.run(
            ["bash", "scripts/build_python_artifacts.sh", destination],
            check=True,
            capture_output=True,
            text=True,
        )
    # Then both exact filename sets and every byte are reproducible
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}
    assert first_files == second_files
    assert len(tuple(first.glob("*.whl"))) == 1
    assert len(tuple(first.glob("*.tar.gz"))) == 1


def test_should_freeze_scoring_only_benchmark_workloads_and_budgets() -> None:
    # Given executable Python and TypeScript release benchmark entry points
    python = Path("benchmarks/release.py").read_text(encoding="utf-8")
    contracts = Path("benchmarks/_contracts.py").read_text(encoding="utf-8")
    typescript = Path("ts/benchmarks/release.mjs").read_text(encoding="utf-8")
    operations = Path("docs/OPERATIONS.md").read_text(encoding="utf-8")
    # When workload contracts are compared to the operator-facing specification
    expected = ("150000", "10000", "p50", "p95", "p99", "peak RSS", "exact SHA")
    # Then every required workload and evidence field is explicit and synchronized
    source = (python + contracts + typescript).replace("_", "")
    assert all(token in source for token in expected[:2])
    assert all(token in operations for token in expected)
    assert "receipt" not in python.lower() + typescript.lower()
    assert "ledger" not in python.lower() + typescript.lower()


def test_should_keep_oidc_jobs_free_of_source_execution_and_long_lived_secrets() -> None:
    # Given the two jobs that can mint a registry identity
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")
    document = pytest.importorskip("yaml").safe_load(workflow)
    jobs = document["jobs"]
    # When each privileged job is inspected structurally
    for name in ("publish-python", "publish-npm"):
        job = jobs[name]
        steps = job["steps"]
        source = json.dumps(steps).lower()
        assert "actions/checkout" not in source
        assert not any(
            token in source
            for token in (
                "uv sync",
                "pnpm",
                "npm install",
                "npm ci",
                "pytest",
                "vitest",
                "scripts/",
                "git ",
            )
        )
        assert "secrets." not in source
        assert job["permissions"] == {"actions": "read", "id-token": "write"}
    assert [step.get("uses", "").split("@")[0] for step in jobs["publish-python"]["steps"]] == [
        "actions/download-artifact",
        "pypa/gh-action-pypi-publish",
    ]
    npm_source = json.dumps(jobs["publish-npm"]["steps"])
    assert npm_source.count("actions/download-artifact@") == 2
    assert npm_source.count("actions/setup-node@") == 1
