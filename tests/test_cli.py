from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from assay.cli import app

_RUNNER = CliRunner()


def _write_request(path: Path) -> None:
    y_true = [0, 1] * 20
    y_score = [0.2, 0.8] * 20
    path.write_text(
        f'{{"metric":"binary","metric_version":"1","y_true":{y_true},"y_score":{y_score}}}'.replace(
            " ", ""
        )
    )


def test_should_keygen_score_and_verify_end_to_end(tmp_path: Path) -> None:
    # Given a signing key and a request on disk
    key_path = tmp_path / "signing.key"
    pub_path = tmp_path / "signing.key.pub"
    assert _RUNNER.invoke(app, ["keygen", "--out", str(key_path)]).exit_code == 0
    assert pub_path.exists()  # keygen also emits the out-of-band public key
    request_path = tmp_path / "req.json"
    _write_request(request_path)
    receipt_path = tmp_path / "receipt.json"
    # When scoring then verifying via the CLI
    scored = _RUNNER.invoke(
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
    verified = _RUNNER.invoke(
        app, ["verify", "--receipt", str(receipt_path), "--public-key", str(pub_path)]
    )
    # Then both succeed and the receipt file exists
    assert scored.exit_code == 0
    assert receipt_path.exists()
    assert verified.exit_code == 0
    assert "OK" in verified.stdout


def test_should_exit_nonzero_when_verifying_a_tampered_receipt(tmp_path: Path) -> None:
    # Given a receipt whose signature was blanked
    key_path = tmp_path / "signing.key"
    pub_path = tmp_path / "signing.key.pub"
    _RUNNER.invoke(app, ["keygen", "--out", str(key_path)])
    request_path = tmp_path / "req.json"
    _write_request(request_path)
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
    # Replace the WHOLE signature: a partial edit can leave valid JSON that fails to
    # parse instead of failing to verify, which would test the parser, not the verifier.
    parsed = json.loads(receipt_path.read_text())
    parsed["signature"] = "00" * 64
    receipt_path.write_text(json.dumps(parsed))
    # When verifying against the pinned public key
    result = _RUNNER.invoke(
        app, ["verify", "--receipt", str(receipt_path), "--public-key", str(pub_path)]
    )
    # Then the CLI exits non-zero AND names the coded cause, not just "it failed"
    assert result.exit_code == 1
    assert "avow.signature_invalid" in result.stdout


def _score_into(tmp_path: Path, ledger: Path) -> None:
    """Drive keygen + score through the CLI so a real ledger exists on disk."""
    key_path = tmp_path / "signing.key"
    _RUNNER.invoke(app, ["keygen", "--out", str(key_path)])
    request_path = tmp_path / "req.json"
    _write_request(request_path)
    _RUNNER.invoke(
        app,
        [
            "score",
            "--request",
            str(request_path),
            "--key",
            str(key_path),
            "--out",
            str(tmp_path / "receipt.json"),
            "--ledger",
            str(ledger),
        ],
    )


def test_should_verify_an_intact_ledger_through_the_cli(tmp_path: Path) -> None:
    # Given a ledger the CLI itself wrote
    ledger = tmp_path / "ledger.jsonl"
    _score_into(tmp_path, ledger)
    # When the ledger is verified through the CLI
    result = _RUNNER.invoke(app, ["verify-ledger", "--ledger", str(ledger)])
    # Then it passes and reports how many entries it checked
    assert result.exit_code == 0
    assert "OK" in result.stdout
    assert "1" in result.stdout


def test_should_fail_closed_when_the_ledger_path_does_not_exist(tmp_path: Path) -> None:
    # Given a ledger path that was never written (a typo is indistinguishable from it)
    missing = tmp_path / "typo.jsonl"
    # When the ledger is verified through the CLI
    result = _RUNNER.invoke(app, ["verify-ledger", "--ledger", str(missing)])
    # Then it exits non-zero and names the coded cause, rather than reporting
    # "0 entries intact" — a fail-open pass for a ledger it never read
    assert result.exit_code == 1
    assert "avow.ledger_unreadable" in result.stdout
    assert "OK" not in result.stdout


def test_should_fail_closed_when_the_ledger_was_tampered_on_disk(tmp_path: Path) -> None:
    # Given a ledger entry edited on disk after it was written
    ledger = tmp_path / "ledger.jsonl"
    _score_into(tmp_path, ledger)
    ledger.write_text(ledger.read_text().replace('"metric":"binary"', '"metric":"forged"'))
    # When the ledger is verified through the CLI
    result = _RUNNER.invoke(app, ["verify-ledger", "--ledger", str(ledger)])
    # Then it exits non-zero and names the coded cause
    assert result.exit_code == 1
    assert "avow.ledger_integrity" in result.stdout
