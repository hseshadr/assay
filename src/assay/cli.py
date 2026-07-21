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
from avow.ledger import append, verify_integrity
from avow.verify import verify_receipt

app = typer.Typer(help="Assay — the scoring engine that refuses to lie.")

# Defaults come from settings, never from literals buried in the command signatures,
# so `ASSAY_SIGNING_KEY_PATH` / `ASSAY_LEDGER_PATH` retune the CLI without code edits.
_SETTINGS = AssaySettings()


def _fail(exc: AvowError) -> None:
    """Report a coded failure and exit non-zero. The stable ``code`` is what callers
    branch on — collapsing it to a bare boolean would throw the cause away."""
    typer.echo(f"FAIL: {exc.code}: {exc}")
    raise typer.Exit(code=1)


@app.command()
def keygen(
    out: Annotated[Path, typer.Option(help="Where to write the signing key.")] = Path(
        _SETTINGS.signing_key_path
    ),
    pub: Annotated[
        Path | None,
        typer.Option(help="Where to write the public key (default: <out>.pub)."),
    ] = None,
) -> None:
    """Generate a new Ed25519 signing key (private seed 0600) plus its public key.

    The public key is written separately so a verifier can pin it out-of-band and
    never has to trust the key embedded in a receipt."""
    key = generate_signing_key()
    save_signing_key(key, path=out)
    pub_path = pub if pub is not None else Path(f"{out}.pub")
    save_public_key(key, path=pub_path)
    typer.echo(f"wrote signing key: {out}")
    typer.echo(f"wrote public key: {pub_path}")


@app.command()
def score(
    request: Annotated[Path, typer.Option("--request", help="ScoreRequest JSON.")],
    key: Annotated[Path, typer.Option("--key", help="Signing key file.")],
    out: Annotated[Path, typer.Option("--out", help="Receipt output path.")],
    ledger: Annotated[Path, typer.Option("--ledger", help="Ledger JSONL path.")] = Path(
        _SETTINGS.ledger_path
    ),
) -> None:
    """Score a classification request and write a signed receipt."""
    parsed = ScoreRequest.model_validate_json(request.read_text(encoding="utf-8"))
    receipt = score_receipt(parsed, signing_key=load_signing_key(key), settings=_SETTINGS)
    out.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    append(receipt, path=ledger)
    typer.echo(f"wrote receipt: {out}")


@app.command()
def composite(
    request: Annotated[Path, typer.Option("--request", help="CompositeRequest JSON.")],
    key: Annotated[Path, typer.Option("--key", help="Signing key file.")],
    out: Annotated[Path, typer.Option("--out", help="Receipt output path.")],
) -> None:
    """Score a weighted multi-scale composite and write a signed receipt."""
    parsed = CompositeRequest.model_validate_json(request.read_text(encoding="utf-8"))
    receipt = composite_score(parsed, signing_key=load_signing_key(key))
    out.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"wrote receipt: {out}")


@app.command()
def verify(
    receipt: Annotated[Path, typer.Option("--receipt", help="Receipt JSON to verify.")],
    public_key: Annotated[
        Path,
        typer.Option("--public-key", help="Pinned signer public-key file (the .pub from keygen)."),
    ],
) -> None:
    """Verify a receipt offline against a pinned signer; exit non-zero if it fails.

    The expected public key is read from ``--public-key`` (out-of-band), never from
    the receipt's own field, so a re-signed forgery cannot authenticate itself. A
    failure reports its coded cause (``avow.signature_invalid`` vs
    ``avow.replay_mismatch``), which a bare pass/fail boolean would discard."""
    parsed = ScoreReceipt.model_validate_json(receipt.read_text(encoding="utf-8"))
    try:
        verify_receipt(parsed, expected_public_key=read_public_key(public_key))
    except AvowError as exc:
        _fail(exc)
    typer.echo("OK: receipt verified")


@app.command()
def verify_ledger(
    ledger: Annotated[Path, typer.Option("--ledger", help="Ledger JSONL path.")] = Path(
        _SETTINGS.ledger_path
    ),
) -> None:
    """Re-derive every ledger entry's hash and fail closed if one was edited on disk.

    This needs no key: identity is the content hash, so on-disk tampering is
    detectable by anyone holding the file, signer or not."""
    try:
        entries = verify_integrity(ledger, ScoreReceipt)
    except AvowError as exc:
        _fail(exc)
    noun = "entry" if len(entries) == 1 else "entries"
    typer.echo(f"OK: ledger verified, {len(entries)} {noun} intact")
