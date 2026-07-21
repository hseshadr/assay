"""The demo is documentation that executes, so it is tested like a contract.

These tests assert on the demo's captured stdout — the computed hash, the calibration
numbers, the composite interval — rather than only on its exit code. The point is that
the test does its own checking instead of delegating that judgment to the demo's
internal ``assert`` statements: gutting what the demo computes fails these tests."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

_EXPECTED_ECE = 0.2
_EXPECTED_BRIER = 0.04
_TOLERANCE = 0.01


def _load_demo() -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "demo" / "run_demo.py"
    spec = importlib.util.spec_from_file_location("run_demo", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    exit_code = _load_demo().main()
    return exit_code, capsys.readouterr().out


def test_should_exit_clean_and_print_all_six_cases(capsys: pytest.CaptureFixture[str]) -> None:
    # Given the runnable demo
    # When main() runs end to end
    exit_code, out = _run(capsys)
    # Then it exits clean having printed exactly six numbered cases, in order
    assert exit_code == 0
    assert re.findall(r"^\[(\d)\]", out, flags=re.MULTILINE) == ["1", "2", "3", "4", "5", "6"]
    assert "all six acceptance cases passed" in out


def test_should_report_a_real_reproducible_hash(capsys: pytest.CaptureFixture[str]) -> None:
    # Given the demo's reproducibility case
    _, out = _run(capsys)
    # Then it prints a genuine sha256 digest, not a placeholder
    match = re.search(r"^\[1\] reproducible: identical hash sha256:([0-9a-f]+)", out, re.MULTILINE)
    assert match is not None, out
    assert len(match.group(1)) >= 16


def test_should_report_verification_tamper_and_abstention(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given the demo's verify, forgery and abstention cases
    _, out = _run(capsys)
    # Then each states the honesty property it proved
    assert "[2] offline verify + replay: signature valid, score recomputes" in out
    assert "[3] tamper + forgery detected" in out
    assert "[4] low sample: abstained, no fake point number emitted" in out


def test_should_report_calibration_numbers_it_actually_computed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given the demo's calibration case
    _, out = _run(capsys)
    # When the printed ECE and Brier are parsed back out
    pattern = r"^\[5\] calibration shipped: ECE=([\d.]+), Brier=([\d.]+)"
    match = re.search(pattern, out, re.MULTILINE)
    assert match is not None, out
    # Then they are the values these fixed inputs must produce
    assert float(match.group(1)) == pytest.approx(_EXPECTED_ECE, abs=_TOLERANCE)
    assert float(match.group(2)) == pytest.approx(_EXPECTED_BRIER, abs=_TOLERANCE)


def test_should_report_the_composite_score_inside_its_interval(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given the demo's weighted-composite case
    _, out = _run(capsys)
    # When the printed score and interval are parsed back out
    match = re.search(r"^\[6\] composite: ([\d.]+) in \[([\d.]+), ([\d.]+)\]", out, re.MULTILINE)
    assert match is not None, out
    score, low, high = (float(group) for group in match.groups())
    # Then the score is the weighted value, bracketed by its interval
    assert score == pytest.approx(0.8)
    assert (low, high) == pytest.approx((0.7, 0.9))
    assert low <= score <= high
