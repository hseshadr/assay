from __future__ import annotations

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
    assert _RUNNER.invoke(app, ["keygen", "--out", str(key_path)]).exit_code == 0
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
    verified = _RUNNER.invoke(app, ["verify", "--receipt", str(receipt_path)])
    # Then both succeed and the receipt file exists
    assert scored.exit_code == 0
    assert receipt_path.exists()
    assert verified.exit_code == 0
    assert "OK" in verified.stdout


def test_should_exit_nonzero_when_verifying_a_tampered_receipt(tmp_path: Path) -> None:
    # Given a receipt whose signature was blanked
    key_path = tmp_path / "signing.key"
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
    tampered = receipt_path.read_text().replace(receipt_path.read_text()[-140:-100], "0" * 40)
    receipt_path.write_text(tampered)
    # When verifying
    result = _RUNNER.invoke(app, ["verify", "--receipt", str(receipt_path)])
    # Then the CLI exits non-zero
    assert result.exit_code == 1
