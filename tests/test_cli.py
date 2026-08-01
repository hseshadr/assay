from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from assay.cli import app

_RUNNER = CliRunner()


def _verify_ledger(tmp_path: Path, ledger: Path, head: Path | None = None):
    """Invoke verify-ledger with both pins supplied out-of-band: the keygen'd public
    key, and the chain head `score` recorded. Neither is read from the ledger."""
    return _RUNNER.invoke(
        app,
        [
            "verify-ledger",
            "--ledger",
            str(ledger),
            "--public-key",
            str(tmp_path / "signing.key.pub"),
            "--head",
            str(head if head is not None else Path(f"{ledger}.head")),
        ],
    )


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
    result = _verify_ledger(tmp_path, ledger)
    # Then it passes and reports how many entries it checked
    assert result.exit_code == 0
    assert "OK" in result.stdout
    assert "1" in result.stdout


# The README's command-line walkthrough uses this exact four-sample request, which is
# below the abstention floor. This test pins what that walkthrough actually produces, so
# the documented tamper step cannot drift away from the file a reader really gets.
_README_REQUEST = (
    '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}'
)


def test_should_detect_the_tamper_the_readme_walkthrough_documents(tmp_path: Path) -> None:
    # Given the ledger the README's own walkthrough produces
    key_path = tmp_path / "signing.key"
    _RUNNER.invoke(app, ["keygen", "--out", str(key_path)])
    request_path = tmp_path / "req.json"
    request_path.write_text(_README_REQUEST)
    ledger = tmp_path / "ledger.jsonl"
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
    stored = ledger.read_text()
    # Then it honestly recorded an abstention — the README tells the reader to edit
    # this field, so it must actually be the field on disk
    assert '"abstained":true' in stored
    # When that abstention is flipped to claim a confident answer it never gave
    ledger.write_text(stored.replace('"abstained":true', '"abstained":false'))
    result = _verify_ledger(tmp_path, ledger)
    # Then the ledger check catches it, exactly as the README shows
    assert result.exit_code == 1
    assert "avow.ledger_integrity" in result.stdout


def test_should_record_the_chain_head_beside_the_ledger_when_scoring(tmp_path: Path) -> None:
    # Given a ledger the CLI wrote
    ledger = tmp_path / "ledger.jsonl"
    _score_twice_into(tmp_path, ledger)
    # Then `score` left the operator a head to carry away, naming the entry count
    pin = Path(f"{ledger}.head")
    assert pin.exists()
    assert json.loads(pin.read_text())["count"] == 2
    # And the ledger verifies against it
    assert _verify_ledger(tmp_path, ledger).exit_code == 0


def test_should_fail_closed_when_the_pinned_head_is_missing(tmp_path: Path) -> None:
    # Given an intact ledger but no pinned head — the verifier has nothing to check the
    # ledger's END against
    ledger = tmp_path / "ledger.jsonl"
    _score_into(tmp_path, ledger)
    # When it is verified against a head file that does not exist
    result = _verify_ledger(tmp_path, ledger, head=tmp_path / "absent.head")
    # Then it fails closed rather than falling back to the head the ledger computes for
    # itself — which would verify every doctored ledger on earth
    assert result.exit_code == 1
    assert "avow.ledger_head_unreadable" in result.stdout
    assert "OK" not in result.stdout


def test_should_fail_closed_when_the_ledger_path_does_not_exist(tmp_path: Path) -> None:
    # Given both pins in hand — public key and chain head — but a ledger path that was
    # never written (a typo is indistinguishable from it)
    ledger = tmp_path / "ledger.jsonl"
    _score_into(tmp_path, ledger)
    missing = tmp_path / "typo.jsonl"
    # When the mistyped ledger is verified through the CLI against the real pin
    result = _verify_ledger(tmp_path, missing, head=Path(f"{ledger}.head"))
    # Then it exits non-zero and names the coded cause, rather than reporting
    # "0 entries intact" — a fail-open pass for a ledger it never read
    assert result.exit_code == 1
    assert "avow.ledger_unreadable" in result.stdout
    assert "OK" not in result.stdout


def _score_twice_into(tmp_path: Path, ledger: Path) -> None:
    """Keygen ONCE, then score twice into the same ledger under that one key.

    Re-running keygen per score would rotate the key and make every earlier entry fail
    the signer check — a pass for the wrong reason. One key, two genuine entries."""
    key_path = tmp_path / "signing.key"
    _RUNNER.invoke(app, ["keygen", "--out", str(key_path)])
    request_path = tmp_path / "req.json"
    _write_request(request_path)
    for index in (1, 2):
        _RUNNER.invoke(
            app,
            [
                "score",
                "--request",
                str(request_path),
                "--key",
                str(key_path),
                "--out",
                str(tmp_path / f"receipt{index}.json"),
                "--ledger",
                str(ledger),
            ],
        )


def test_should_reject_a_ledger_an_entry_was_deleted_from_through_the_cli(tmp_path: Path) -> None:
    # Given a two-entry ledger the CLI itself wrote under ONE key, with its second entry
    # dropped — the surviving line is untouched and genuinely signed by the pinned key
    ledger = tmp_path / "ledger.jsonl"
    _score_twice_into(tmp_path, ledger)
    assert len(ledger.read_text().splitlines()) == 2
    ledger.write_text(ledger.read_text().splitlines()[0] + "\n")
    # When the ledger is verified through the CLI
    result = _verify_ledger(tmp_path, ledger)
    # Then the operator is told the audit is broken, not handed a clean bill of health
    assert result.exit_code == 1
    assert "avow.ledger_integrity" in result.stdout
    assert "OK" not in result.stdout


def test_should_fail_closed_when_the_ledger_was_tampered_on_disk(tmp_path: Path) -> None:
    # Given a ledger entry edited on disk after it was written
    ledger = tmp_path / "ledger.jsonl"
    _score_into(tmp_path, ledger)
    ledger.write_text(ledger.read_text().replace('"metric":"binary"', '"metric":"forged"'))
    # When the ledger is verified through the CLI
    result = _verify_ledger(tmp_path, ledger)
    # Then it exits non-zero and names the coded cause
    assert result.exit_code == 1
    assert "avow.ledger_integrity" in result.stdout
