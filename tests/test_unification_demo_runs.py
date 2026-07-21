"""The unification demo's claim is that ONE envelope and ONE verifier serve both the
score face and the effect face. These tests read that claim back out of the demo's
captured stdout — which subjects were verified, that the allowed effect ran and the
denied one did not — instead of trusting its exit code alone."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest


def _load_demo() -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "demo" / "unification_demo.py"
    spec = importlib.util.spec_from_file_location("unification_demo", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    exit_code = _load_demo().main()
    return exit_code, capsys.readouterr().out


def test_should_exit_clean_and_state_what_it_proved(capsys: pytest.CaptureFixture[str]) -> None:
    # Given the runnable unification demo
    # When main() runs end to end (score face + effect face, allow + deny)
    exit_code, out = _run(capsys)
    # Then it exits clean and states the claim it just demonstrated
    assert exit_code == 0
    assert "unification proven" in out
    assert "serve both the score and effect faces" in out


def test_should_report_a_verified_score_receipt(capsys: pytest.CaptureFixture[str]) -> None:
    # Given the score face
    _, out = _run(capsys)
    # Then a real score was computed and its receipt verified
    match = re.search(r"^\[score\] Assay score=([\d.]+) -> signed receipt verified", out, re.M)
    assert match is not None, out
    assert 0.0 <= float(match.group(1)) <= 1.0


def test_should_run_the_allowed_effect_and_block_the_denied_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given the effect face gating one allowed and one denied action
    _, out = _run(capsys)
    # Then the allowed action ran under a signed receipt
    assert "[writ allow] 'read' ran -> signed allow receipt verified" in out
    # And the denied action was blocked with a signed denial and no effect
    assert "[writ deny]  'delete' blocked -> signed denial verified, no effect" in out


def test_should_verify_score_and_effect_subjects_under_one_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given the unification proof line
    _, out = _run(capsys)
    match = re.search(r"^\[proof\] one verify_receipt verified subjects \((.+?)\)", out, re.M)
    assert match is not None, out
    subjects = re.findall(r"'([A-Za-z]+)'", match.group(1))
    # Then one verifier checked three receipts: one score subject and two effect subjects
    assert subjects == ["ReceiptPayload", "EffectSubject", "EffectSubject"]
    assert "under one pinned key" in out
