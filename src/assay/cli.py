"""Typer CLI. Thin command layer: parse files into typed models, delegate to the
facade, translate results to exit codes. No business logic lives here."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from assay.api import composite_score
from assay.api import score as score_receipt
from assay.api import verify as verify_receipt_bool
from assay.keys import (
    generate_signing_key,
    load_signing_key,
    read_public_key,
    save_public_key,
    save_signing_key,
)
from assay.ledger import append
from assay.models import CompositeRequest, ScoreRequest
from assay.receipt import ScoreReceipt
from assay.settings import AssaySettings

app = typer.Typer(help="Assay — the scoring engine that refuses to lie.")


@app.command()
def keygen(
    out: Annotated[Path, typer.Option(help="Where to write the signing key.")] = Path(
        "signing.key"
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
    ledger: Annotated[Path, typer.Option("--ledger", help="Ledger JSONL path.")],
) -> None:
    """Score a classification request and write a signed receipt."""
    parsed = ScoreRequest.model_validate_json(request.read_text(encoding="utf-8"))
    receipt = score_receipt(parsed, signing_key=load_signing_key(key), settings=AssaySettings())
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
    the receipt's own field, so a re-signed forgery cannot authenticate itself."""
    parsed = ScoreReceipt.model_validate_json(receipt.read_text(encoding="utf-8"))
    expected = read_public_key(public_key)
    if verify_receipt_bool(parsed, expected_public_key=expected):
        typer.echo("OK: receipt verified")
        return
    typer.echo("FAIL: receipt did not verify")
    raise typer.Exit(code=1)
