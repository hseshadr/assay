"""GitHub Actions must resolve third-party code from immutable commits.

A tag (even a release tag like `ci-v2`) can be repointed at new code by whoever
owns the upstream repo; a full 40-hex commit SHA cannot. Pinning is what turns
"trust the publisher forever" into "trust exactly these bytes", so every
`uses:` in this repo — including reusable workflows we own, such as
`hseshadr/ci` — resolves to a commit. Local `./...` references are exempt:
they resolve inside this repo, at this commit, by definition.

Two ways a guard like this rots into a no-op, both closed here:

* it globs `*.yml` only, so a `*.yaml` workflow is never scanned at all; and
* it passes *vacuously* when the scan finds nothing — a moved or renamed workflow
  directory would turn the guard green instead of red.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")


def _scan(directory: Path) -> tuple[list[str], int]:
    """Return (unpinned external refs, total external refs) across every workflow.

    GitHub honours BOTH `.yml` and `.yaml`, so scanning one extension leaves the other
    as an unguarded path. The ref count comes back too, so a caller can assert the scan
    actually examined something rather than trusting an empty failure list."""
    unpinned: list[str] = []
    scanned = 0
    for workflow in sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")]):
        for action in USES.findall(workflow.read_text(encoding="utf-8")):
            if action.startswith("./"):
                continue
            scanned += 1
            if PINNED.fullmatch(action) is None:
                unpinned.append(f"{workflow.name}: {action}")
    return unpinned, scanned


def test_external_actions_are_pinned_to_full_commit_shas() -> None:
    # Given every workflow this repo actually ships
    unpinned, scanned = _scan(ROOT / ".github/workflows")
    # Then none of them resolves to a mutable ref
    assert unpinned == []
    # ...and the scan was not vacuous: it really did examine external refs, so an
    # emptied or renamed workflow directory fails here instead of passing silently.
    assert scanned > 0


def test_the_guard_scans_yaml_as_well_as_yml_workflows(tmp_path: Path) -> None:
    # Given an unpinned action hidden in a `.yaml` file — the extension GitHub also honours
    (tmp_path / "sneaky.yaml").write_text(
        "jobs:\n  a:\n    steps:\n      - uses: attacker/action@v1\n", encoding="utf-8"
    )
    # When the guard scans
    unpinned, scanned = _scan(tmp_path)
    # Then the `.yaml` file is caught rather than skipped
    assert scanned == 1
    assert unpinned == ["sneaky.yaml: attacker/action@v1"]


def test_the_guard_finds_no_refs_in_an_empty_directory(tmp_path: Path) -> None:
    # Given a directory holding no workflows (what a moved or renamed dir looks like)
    unpinned, scanned = _scan(tmp_path)
    # Then there is nothing to report — and that empty report is precisely the vacuous
    # "pass" the `scanned > 0` assertion above converts into a failure.
    assert unpinned == []
    assert scanned == 0


def _yaml(path: Path) -> dict[object, object]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_scheduled_security_audit_covers_python_and_typescript() -> None:
    workflow = _yaml(ROOT / ".github/workflows/security-audit.yml")
    triggers = workflow.get("on", workflow.get(True))
    jobs = workflow["jobs"]
    source = (ROOT / ".github/workflows/security-audit.yml").read_text(encoding="utf-8")

    assert isinstance(triggers, dict)
    assert {"schedule", "workflow_dispatch"} <= set(triggers)
    assert isinstance(jobs, dict)
    assert {"pip-audit", "pnpm-audit"} <= set(jobs)
    assert "pnpm audit --audit-level low" in source
    package = json.loads((ROOT / "ts/package.json").read_text(encoding="utf-8"))
    version = package["packageManager"].removeprefix("pnpm@")
    assert f"version: {version}" in source


def test_dependency_update_intake_covers_both_package_ecosystems() -> None:
    updates = _yaml(ROOT / ".github/dependabot.yml")["updates"]
    assert isinstance(updates, list)
    ecosystems = {entry["package-ecosystem"] for entry in updates}
    assert {"github-actions", "npm", "pip"} <= ecosystems


def test_checkout_never_persists_push_credentials() -> None:
    workflows = (ROOT / ".github/workflows").glob("*.yml")
    offenders = []
    for workflow in workflows:
        source = workflow.read_text(encoding="utf-8")
        checkouts = re.findall(
            r"uses: actions/checkout@.*?(?=\n\s*- (?:name:|uses:)|\Z)", source, re.S
        )
        offenders.extend(
            f"{workflow.name}:{index}"
            for index, block in enumerate(checkouts)
            if "persist-credentials: false" not in block
        )
    assert offenders == []
