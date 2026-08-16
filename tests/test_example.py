"""Run the realistic Northstar example through clean built artifacts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "examples" / "run_composite.sh"
_REQUEST = _ROOT / "examples" / "northstar_score.json"
_VECTORS = _ROOT / "testdata" / "vectors" / "composition.json"
_MULTIPLY = "\N{MULTIPLICATION SIGN}"
_EXPECTED = f"""Northstar weighted score: 0.92
Method: weighted_mean @ northstar.2026-08-12
Interval: null — all inputs are deterministic

security       19/20  -> 0.950000 {_MULTIPLY} 0.20 = 0.19
privacy        15/15  -> 1.000000 {_MULTIPLY} 0.15 = 0.15
reliability    15/15  -> 1.000000 {_MULTIPLY} 0.15 = 0.15
performance    12/15  -> 0.800000 {_MULTIPLY} 0.15 = 0.12
correctness    15/15  -> 1.000000 {_MULTIPLY} 0.15 = 0.15
clarity        14/15  -> 0.933333 {_MULTIPLY} 0.15 = 0.14
production       2/5  -> 0.400000 {_MULTIPLY} 0.05 = 0.02

Total: 0.92
inputs_hash: sha256:0266b1c59c97bacf85dc945685c55bb4386856b525249c7d5663a8edf020ba06
Parity: Python and TypeScript fields and values match
"""


def _northstar_vector() -> dict[str, object]:
    vectors: list[dict[str, object]] = json.loads(_VECTORS.read_text(encoding="utf-8"))
    return next(vector for vector in vectors if vector["id"] == "northstar_uncapped_weighted")


def _tree_state() -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],  # noqa: S607
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _run_example(cwd: Path) -> subprocess.CompletedProcess[str]:
    before = _tree_state()
    completed = subprocess.run(  # noqa: S603 - repository script is the test subject
        ["bash", str(_SCRIPT)],  # noqa: S607 - fixed shell interpreter
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    assert _tree_state() == before
    return completed


@pytest.fixture(scope="module")
def example_runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[subprocess.CompletedProcess[str], ...]:
    unrelated = tmp_path_factory.mktemp("unrelated")
    return _run_example(_ROOT), _run_example(unrelated)


def test_should_copy_only_the_committed_northstar_request() -> None:
    # Given the committed Northstar parity vector and public example request
    vector = _northstar_vector()
    request = json.loads(_REQUEST.read_text(encoding="utf-8"))
    # When their request objects are compared directly
    # Then no vector metadata or oracle output leaked into the public input
    assert tuple(request) == ("method", "method_version", "components", "clamp")
    assert request == vector["request"]


def test_should_run_built_artifacts_from_repository_and_unrelated_directories(
    example_runs: tuple[subprocess.CompletedProcess[str], ...],
) -> None:
    # Given two executions with different current working directories
    # When each builds and installs the real wheel and npm tarball
    # Then both complete silently except for the one shared human explanation
    for completed in example_runs:
        assert completed.returncode == 0, completed.stderr
        assert completed.stderr == ""
        assert completed.stdout == _EXPECTED


def test_should_print_each_result_summary_line_once(
    example_runs: tuple[subprocess.CompletedProcess[str], ...],
) -> None:
    # Given the artifact-parity explanation
    output = example_runs[0].stdout
    # When its result footer is counted
    # Then one language-neutral score, total, hash, and parity verdict are shown
    assert output.count("Northstar weighted score:") == 1
    assert output.count("Total:") == 1
    assert output.count("inputs_hash:") == 1
    assert output.count("Parity:") == 1
