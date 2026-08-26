"""Executable security contracts for Assay's thin GitHub ingress."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOW_ROOT = ROOT / ".github/workflows"
WORKFLOW_NAMES = {"dagger.yml", "publish.yml", "release-candidate.yml", "security-audit.yml"}
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return cast(dict[str, object], value)


def _workflow(name: str) -> dict[str, object]:
    loader = yaml.BaseLoader((WORKFLOW_ROOT / name).read_text(encoding="utf-8"))
    try:
        return _mapping(loader.get_single_data())
    finally:
        loader.dispose()


def _jobs(workflow: dict[str, object]) -> dict[str, object]:
    return _mapping(workflow["jobs"])


def _job(workflow: dict[str, object], name: str) -> dict[str, object]:
    return _mapping(_jobs(workflow)[name])


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    value = job["steps"]
    assert isinstance(value, list)
    return [_mapping(step) for step in value]


def _uses(job: dict[str, object]) -> tuple[str, ...]:
    return tuple(str(step["uses"]) for step in _steps(job) if "uses" in step)


def _with(step: dict[str, object]) -> dict[str, object]:
    return _mapping(step.get("with", {}))


def _action(name: str, job: dict[str, object]) -> dict[str, object]:
    matches = [step for step in _steps(job) if str(step.get("uses", "")).startswith(f"{name}@")]
    assert len(matches) == 1
    return matches[0]


def test_should_ship_only_the_four_dagger_ingress_workflows() -> None:
    # Given / When
    names = {path.name for path in WORKFLOW_ROOT.iterdir() if path.suffix in {".yml", ".yaml"}}

    # Then
    assert names == WORKFLOW_NAMES
    assert all(_jobs(_workflow(name)) for name in names)


def test_should_pin_every_external_action_and_disable_checkout_credentials() -> None:
    # Given
    workflows = tuple(_workflow(name) for name in WORKFLOW_NAMES)

    # When
    jobs = [_mapping(job) for workflow in workflows for job in _jobs(workflow).values()]
    uses = [reference for job in jobs for reference in _uses(job)]
    checkouts = [
        step
        for job in jobs
        for step in _steps(job)
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]

    # Then
    assert uses
    assert all(PINNED.fullmatch(reference) for reference in uses)
    assert all(_with(step).get("persist-credentials") == "false" for step in checkouts)


def test_should_make_ci_one_checkout_and_one_dagger_call() -> None:
    # Given
    workflow = _workflow("dagger.yml")
    job = _job(workflow, "dagger")

    # When
    dagger_step = _action("dagger/dagger-for-github", job)

    # Then
    assert set(_mapping(workflow["on"])) == {"push", "pull_request"}
    assert _uses(job) == (
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "dagger/dagger-for-github@496f1b3d8b0d823834c13e67cf8a8e08ca3b9602",
    )
    assert all("run" not in step for step in _steps(job))
    assert _with(dagger_step) == {
        "version": "0.21.8",
        "verb": "call",
        "args": "ci --commit-sha=${{ github.sha }}",
    }


def test_should_make_the_schedule_one_complete_dagger_security_call() -> None:
    # Given
    workflow = _workflow("security-audit.yml")
    job = _job(workflow, "security")

    # When
    dagger_step = _action("dagger/dagger-for-github", job)

    # Then
    assert set(_mapping(workflow["on"])) == {"schedule", "workflow_dispatch"}
    assert len(_steps(job)) == 2
    assert all("run" not in step for step in _steps(job))
    assert _with(dagger_step)["args"] == "security --commit-sha=${{ github.sha }}"


def test_should_build_and_upload_only_a_manual_default_branch_candidate() -> None:
    # Given
    workflow = _workflow("release-candidate.yml")
    job = _job(workflow, "candidate")

    # When
    dagger_step = _action("dagger/dagger-for-github", job)
    upload = _action("actions/upload-artifact", job)

    # Then
    assert set(_mapping(workflow["on"])) == {"workflow_dispatch"}
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert all("run" not in step for step in _steps(job))
    assert "release-candidate --tag=${{ inputs.tag }}" in str(_with(dagger_step)["args"])
    assert "--commit-sha=${{ github.sha }}" in str(_with(dagger_step)["args"])
    assert _with(upload) == {
        "name": "assay-${{ github.sha }}",
        "path": "candidate/",
        "if-no-files-found": "error",
        "retention-days": "1",
    }


def test_should_keep_both_privileged_publishers_source_free() -> None:
    # Given
    workflow = _workflow("publish.yml")
    publishers = tuple(_mapping(job) for job in _jobs(workflow).values())

    # When
    sources = [str(step.get("uses", "")) for job in publishers for step in _steps(job)]
    commands = [step for job in publishers for step in _steps(job) if "run" in step]

    # Then
    assert set(_mapping(workflow["on"])) == {"workflow_run"}
    assert not any(reference.startswith("actions/checkout@") for reference in sources)
    assert not any("setup-" in reference or "action-setup" in reference for reference in sources)
    assert commands == []
    assert all(job["environment"] == "npm-release" for job in publishers)
    assert all(
        _mapping(job["permissions"])
        == {
            "actions": "read",
            "id-token": "write",
        }
        for job in publishers
    )


def test_should_bind_download_and_remote_dagger_to_the_candidate_run_identity() -> None:
    # Given
    workflow = _workflow("publish.yml")

    # When / Then
    for job in (_mapping(value) for value in _jobs(workflow).values()):
        download = _action("actions/download-artifact", job)
        assert _with(download) == {
            "name": "assay-${{ github.event.workflow_run.head_sha }}",
            "path": "candidate",
            "github-token": "${{ github.token }}",
            "run-id": "${{ github.event.workflow_run.id }}",
        }
        dagger_step = _action("dagger/dagger-for-github", job)
        assert _with(dagger_step)["module"] == (
            "github.com/hseshadr/assay@${{ github.event.workflow_run.head_sha }}"
        )


def test_should_gate_publishers_on_successful_manual_default_branch_candidate() -> None:
    # Given / When
    jobs = _jobs(_workflow("publish.yml"))
    conditions = {str(_mapping(job)["if"]) for job in jobs.values()}

    # Then
    assert conditions == {
        "github.event.workflow_run.conclusion == 'success' && "
        "github.event.workflow_run.event == 'workflow_dispatch' && "
        "github.event.workflow_run.head_branch == github.event.repository.default_branch"
    }


def test_should_give_no_fork_or_shell_path_privileged_base_authority() -> None:
    # Given
    source = "\n".join(
        (WORKFLOW_ROOT / name).read_text(encoding="utf-8") for name in WORKFLOW_NAMES
    )

    # When / Then
    assert "pull_request_target" not in source
    assert "dangerously-allow-all-builds" not in source
    assert "secrets." not in source


def test_should_serialize_every_graph_and_scope_the_one_trigger_exception() -> None:
    # Given
    workflows = {name: _workflow(name) for name in WORKFLOW_NAMES}
    sources = {name: (WORKFLOW_ROOT / name).read_text(encoding="utf-8") for name in WORKFLOW_NAMES}

    # When / Then
    for workflow in workflows.values():
        concurrency = _mapping(workflow["concurrency"])
        assert str(concurrency["group"]).startswith("assay-")
        assert concurrency["cancel-in-progress"] in {"true", "false"}
    exception = "zizmor: ignore[dangerous-triggers]"
    assert exception in sources["publish.yml"]
    assert sum(source.count(exception) for source in sources.values()) == 1
