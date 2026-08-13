"""Typer CLI. Thin command layer: parse files into typed models, delegate to the
facade, translate results to exit codes. No business logic lives here."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from assay.api import composite_score
from assay.api import score as score_receipt
from assay.models import CompositeRequest, ScoreRequest
from assay.receipt import ScoreReceipt
from assay.settings import AssaySettings
from avow.errors import AvowError
from avow.keys import (
    generate_signing_key,
    load_signing_key,
    read_public_key,
    save_public_key,
    save_signing_key,
)
from avow.ledger import append_and_save_head, read_head, verify_integrity
from avow.verify import verify_receipt

app = typer.Typer(help="Assay — the scoring engine that refuses to lie.")

# Defaults come from settings, never from literals buried in the command signatures,
# so `ASSAY_SIGNING_KEY_PATH` / `ASSAY_LEDGER_PATH` retune the CLI without code edits.
_SETTINGS = AssaySettings()
_DEFAULT_KEY_PATH = Path(_SETTINGS.signing_key_path)
_DEFAULT_LEDGER_PATH = Path(_SETTINGS.ledger_path)

_KeyOutput = Annotated[Path, typer.Option(help="Where to write the signing key.")]
_PublicOutput = Annotated[Path | None, typer.Option(help="Public-key output; default <out>.pub.")]
_RequestInput = Annotated[Path, typer.Option("--request", help="Typed request JSON.")]
_SigningKeyInput = Annotated[Path, typer.Option("--key", help="Signing key file.")]
_ReceiptOutput = Annotated[Path, typer.Option("--out", help="Receipt output path.")]
_LedgerInput = Annotated[Path, typer.Option("--ledger", help="Ledger JSONL path.")]
_HeadOutput = Annotated[
    Path | None, typer.Option("--head", help="Head output; default <ledger>.head.")
]
_ReceiptInput = Annotated[Path, typer.Option("--receipt", help="Receipt JSON to verify.")]
_PublicKeyInput = Annotated[Path, typer.Option("--public-key", help="Pinned signer public key.")]
_HeadInput = Annotated[Path, typer.Option("--head", help="Pinned chain-head file.")]


def _fail(exc: AvowError) -> None:
    """Report a coded failure and exit non-zero. The stable ``code`` is what callers
    branch on — collapsing it to a bare boolean would throw the cause away."""
    typer.echo(f"FAIL: {exc.code}: {exc}")
    raise typer.Exit(code=1)


@app.command()
def keygen(
    out: _KeyOutput = _DEFAULT_KEY_PATH,
    pub: _PublicOutput = None,
) -> None:
    """Generate a private Ed25519 seed plus its separately pinnable public key."""
    key = generate_signing_key()
    save_signing_key(key, path=out)
    pub_path = pub if pub is not None else Path(f"{out}.pub")
    save_public_key(key, path=pub_path)
    typer.echo(f"wrote signing key: {out}")
    typer.echo(f"wrote public key: {pub_path}")


@app.command()
def score(
    request: _RequestInput,
    key: _SigningKeyInput,
    out: _ReceiptOutput,
    ledger: _LedgerInput = _DEFAULT_LEDGER_PATH,
    head: _HeadOutput = None,
) -> None:
    """Score, sign, then durably extend the ledger and its convenience pin."""
    parsed = ScoreRequest.model_validate_json(request.read_text(encoding="utf-8"))
    receipt = score_receipt(parsed, signing_key=load_signing_key(key), settings=_SETTINGS)
    out.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    head_path = head if head is not None else Path(f"{ledger}.head")
    new_head = append_and_save_head(receipt, path=ledger, head_path=head_path)
    typer.echo(f"wrote receipt: {out}")
    typer.echo(f"wrote ledger head: {head_path} ({new_head.count} entries)")


@app.command()
def composite(
    request: _RequestInput,
    key: _SigningKeyInput,
    out: _ReceiptOutput,
) -> None:
    """Score a weighted multi-scale composite and write a signed receipt."""
    parsed = CompositeRequest.model_validate_json(request.read_text(encoding="utf-8"))
    receipt = composite_score(parsed, signing_key=load_signing_key(key))
    out.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"wrote receipt: {out}")


@app.command()
def verify(
    receipt: _ReceiptInput,
    public_key: _PublicKeyInput,
) -> None:
    """Verify offline against a pinned signer; this does not prove freshness."""
    parsed = ScoreReceipt.model_validate_json(receipt.read_text(encoding="utf-8"))
    try:
        verify_receipt(parsed, expected_public_key=read_public_key(public_key))
    except AvowError as exc:
        _fail(exc)
    typer.echo("OK: receipt verified")


@app.command()
def verify_ledger(
    public_key: _PublicKeyInput,
    head: _HeadInput,
    ledger: _LedgerInput = _DEFAULT_LEDGER_PATH,
) -> None:
    """Verify every ledger entry and link against caller-supplied signer and head pins."""
    try:
        entries = _ledger_entries(public_key, head, ledger)
    except AvowError as exc:
        _fail(exc)
    noun = "entry" if len(entries) == 1 else "entries"
    typer.echo(f"OK: ledger verified, {len(entries)} {noun} intact")


def _ledger_entries(public_key: Path, head: Path, ledger: Path) -> tuple[ScoreReceipt, ...]:
    return verify_integrity(
        ledger,
        ScoreReceipt,
        expected_public_key=read_public_key(public_key),
        expected_head=read_head(head),
    )
