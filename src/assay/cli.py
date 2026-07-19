"""Typer CLI. Thin command layer: parse files into typed models, delegate to the
facade, translate results to exit codes. No business logic lives here."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from assay.api import composite_score
from assay.api import score as score_receipt
from assay.api import verify as verify_receipt_bool
from assay.keys import generate_signing_key, load_signing_key, save_signing_key
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
) -> None:
    """Generate a new Ed25519 signing key (written 0600)."""
    save_signing_key(generate_signing_key(), path=out)
    typer.echo(f"wrote signing key: {out}")


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
) -> None:
    """Verify a receipt offline; exit non-zero if it fails."""
    parsed = ScoreReceipt.model_validate_json(receipt.read_text(encoding="utf-8"))
    if verify_receipt_bool(parsed):
        typer.echo("OK: receipt verified")
        return
    typer.echo("FAIL: receipt did not verify")
    raise typer.Exit(code=1)
