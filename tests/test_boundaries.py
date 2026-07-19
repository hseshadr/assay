"""Fail-closed boundary tests: every input guard and CLI failure path is exercised
like a feature, so the honesty promise ("never emit what the data cannot support")
is enforced, not just asserted in prose."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from assay.cli import app
from assay.composite import SubScore, composite
from assay.errors import InvalidScoreRequest
from assay.keys import load_signing_key
from assay.metrics import binary_scores
from assay.receipt import ScoreReceipt

_RUNNER = CliRunner()


def test_should_reject_when_lengths_mismatch() -> None:
    # Given y_true and y_score of different lengths
    # When scored
    # Then it fails closed
    with pytest.raises(InvalidScoreRequest):
        binary_scores([0, 1], [0.2])


def test_should_reject_when_inputs_are_empty() -> None:
    # Given empty inputs
    # When scored
    # Then it fails closed
    with pytest.raises(InvalidScoreRequest):
        binary_scores([], [])


def test_should_reject_composite_when_weights_are_not_positive() -> None:
    # Given three valid-scale sub-scores whose weights sum to zero
    subs = [
        SubScore("a", 0.5, 0.4, 0.6, 0.0, 1.0, 0.0),
        SubScore("b", 0.5, 0.4, 0.6, 0.0, 1.0, 0.0),
        SubScore("c", 0.5, 0.4, 0.6, 0.0, 1.0, 0.0),
    ]
    # When composited
    # Then it is rejected (a zero-weight composite has no meaning)
    with pytest.raises(InvalidScoreRequest):
        composite(subs)


def test_should_reject_signing_key_of_wrong_length(tmp_path: Path) -> None:
    # Given a key file that is not a 32-byte seed
    path = tmp_path / "bad.key"
    path.write_bytes(b"too-short")
    # When loaded
    # Then it fails closed
    with pytest.raises(ValueError, match="32 bytes"):
        load_signing_key(path)


def _keygen(tmp_path: Path) -> Path:
    key_path = tmp_path / "signing.key"
    _RUNNER.invoke(app, ["keygen", "--out", str(key_path)])
    return key_path


def test_should_composite_via_cli_end_to_end(tmp_path: Path) -> None:
    # Given a composite request on disk and a key
    key_path = _keygen(tmp_path)
    request_path = tmp_path / "composite.json"
    request_path.write_text(
        '{"metric_version":"1","subscores":['
        '{"name":"a","value":0.9,"low":0.85,"high":0.95,'
        '"scale_min":0.0,"scale_max":1.0,"weight":1.0},'
        '{"name":"b","value":80.0,"low":70.0,"high":90.0,'
        '"scale_min":0.0,"scale_max":100.0,"weight":1.0},'
        '{"name":"c","value":4.0,"low":3.5,"high":4.5,'
        '"scale_min":1.0,"scale_max":5.0,"weight":2.0}]}'
    )
    receipt_path = tmp_path / "receipt.json"
    # When run through the composite command
    result = _RUNNER.invoke(
        app,
        [
            "composite",
            "--request",
            str(request_path),
            "--key",
            str(key_path),
            "--out",
            str(receipt_path),
        ],
    )
    # Then it succeeds and writes a verifiable receipt
    assert result.exit_code == 0
    assert receipt_path.exists()


def test_should_report_fail_when_signature_is_blanked(tmp_path: Path) -> None:
    # Given a validly-parsed receipt whose signature was replaced with zeros
    key_path = _keygen(tmp_path)
    request_path = tmp_path / "req.json"
    request_path.write_text(
        '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}'
    )
    receipt_path = tmp_path / "receipt.json"
    _RUNNER.invoke(
        app,
        [
            "score",
            "--request",
            str(request_path),
            "--key",
            str(key_path),
            "--out",
            str(receipt_path),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
        ],
    )
    receipt = ScoreReceipt.model_validate_json(receipt_path.read_text())
    blanked = receipt.model_copy(update={"signature": "00" * 64})
    receipt_path.write_text(blanked.model_dump_json())
    # When verified against the pinned public key
    pub_path = Path(f"{key_path}.pub")
    result = _RUNNER.invoke(
        app, ["verify", "--receipt", str(receipt_path), "--public-key", str(pub_path)]
    )
    # Then the CLI reports failure on the clean verify path and exits non-zero
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
