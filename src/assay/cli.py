"""Typer CLI. Thin command layer: parse files into typed models, delegate to the
facade, translate results to exit codes. No business logic lives here."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from assay.api import composite_score
from assay.api import score as score_receipt
from assay.errors import AssayError, CliInputInvalid, InvalidScoreRequest
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
from avow.ledger import LedgerHead, append_and_save_head, read_head, verify_integrity
from avow.verify import verify_receipt

app = typer.Typer(help="Assay — the scoring engine that refuses to lie.")

_KeyOutput = Annotated[Path | None, typer.Option(help="Where to write the signing key.")]
_PublicOutput = Annotated[Path | None, typer.Option(help="Public-key output; default <out>.pub.")]
_RequestInput = Annotated[Path, typer.Option("--request", help="Typed request JSON.")]
_SigningKeyInput = Annotated[Path, typer.Option("--key", help="Signing key file.")]
_ReceiptOutput = Annotated[Path, typer.Option("--out", help="Receipt output path.")]
_LedgerInput = Annotated[Path | None, typer.Option("--ledger", help="Ledger JSONL path.")]
_HeadOutput = Annotated[
    Path | None, typer.Option("--head", help="Head output; default <ledger>.head.")
]
_ReceiptInput = Annotated[Path, typer.Option("--receipt", help="Receipt JSON to verify.")]
_PublicKeyInput = Annotated[Path, typer.Option("--public-key", help="Pinned signer public key.")]
_HeadInput = Annotated[Path, typer.Option("--head", help="Pinned chain-head file.")]
_SAFE_FIELDS = frozenset(
    {"metric", "metric_version", "y_true", "y_score", "threshold", "subscores"}
)


def _safe_token(token: object) -> str:
    """Render only schema-owned field names and numeric positions."""
    if isinstance(token, int):
        return str(token)
    return token if isinstance(token, str) and token in _SAFE_FIELDS else "field"


def _safe_location(exc: ValidationError) -> str:
    """Extract one schema location without serialising its private input value."""
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    location = errors[0].get("loc", ()) if errors else ()
    rendered = ".".join(_safe_token(token) for token in location)
    return rendered or "request"


def _fail_code(code: str, *, field: str | None = None) -> NoReturn:
    """Emit a machine-stable code and optional schema location, never an exception."""
    suffix = f" field={field}" if field is not None else ""
    typer.echo(f"FAIL: {code}{suffix}")
    raise typer.Exit(code=1)


def _fail(exc: AssayError | AvowError) -> NoReturn:
    """Report a domain code without interpolating caller-controlled error messages."""
    _fail_code(exc.code)


def _fail_validation(exc: ValidationError, *, code: str) -> NoReturn:
    """Report only the typed boundary and safe schema path."""
    _fail_code(code, field=_safe_location(exc))


def _load_settings() -> AssaySettings:
    """Resolve environment settings only inside a redacting command boundary."""
    try:
        return AssaySettings()
    except ValidationError as exc:
        _fail_validation(exc, code=CliInputInvalid.code)


def _key_paths(out: Path | None, pub: Path | None) -> tuple[Path, Path]:
    """Resolve key destinations lazily so help never evaluates the environment."""
    private = out if out is not None else Path(_load_settings().signing_key_path)
    public = pub if pub is not None else Path(f"{private}.pub")
    return private, public


@app.command()
def keygen(
    out: _KeyOutput = None,
    pub: _PublicOutput = None,
) -> None:
    """Generate a private Ed25519 seed plus its separately pinnable public key."""
    out_path, pub_path = _key_paths(out, pub)
    try:
        key = generate_signing_key()
        save_signing_key(key, path=out_path)
        save_public_key(key, path=pub_path)
    except OSError:
        _fail(CliInputInvalid("key destinations are not writable"))
    typer.echo(f"wrote signing key: {out_path}")
    typer.echo(f"wrote public key: {pub_path}")


def _write_score(
    request: Path,
    key: Path,
    out: Path,
    ledger: Path,
    head_path: Path,
    settings: AssaySettings,
) -> LedgerHead:
    parsed = ScoreRequest.model_validate_json(request.read_text(encoding="utf-8"))
    receipt = score_receipt(parsed, signing_key=load_signing_key(key), settings=settings)
    out.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    return append_and_save_head(receipt, path=ledger, head_path=head_path)


def _score_runtime(ledger: Path | None, head: Path | None) -> tuple[AssaySettings, Path, Path]:
    """Resolve settings and derived persistence paths at command execution time."""
    settings = _load_settings()
    ledger_path = ledger if ledger is not None else Path(settings.ledger_path)
    head_path = head if head is not None else Path(f"{ledger_path}.head")
    return settings, ledger_path, head_path


def _run_score(
    request: Path, key: Path, out: Path, ledger: Path | None, head: Path | None
) -> tuple[LedgerHead, Path]:
    """Translate every private scoring failure to one safe public boundary."""
    settings, ledger_path, head_path = _score_runtime(ledger, head)
    try:
        new_head = _write_score(request, key, out, ledger_path, head_path, settings)
    except ValidationError as exc:
        _fail_validation(exc, code=InvalidScoreRequest.code)
    except (AssayError, AvowError) as exc:
        _fail(exc)
    except (OSError, ValueError):
        _fail(CliInputInvalid("score input is unreadable or malformed"))
    return new_head, head_path


@app.command()
def score(
    request: _RequestInput,
    key: _SigningKeyInput,
    out: _ReceiptOutput,
    ledger: _LedgerInput = None,
    head: _HeadOutput = None,
) -> None:
    """Score, sign, and durably extend the ledger and convenience pin."""
    new_head, head_path = _run_score(request, key, out, ledger, head)
    typer.echo(f"wrote receipt: {out}")
    typer.echo(f"wrote ledger head: {head_path} ({new_head.count} entries)")


def _write_composite(request: Path, key: Path, out: Path) -> None:
    parsed = CompositeRequest.model_validate_json(request.read_text(encoding="utf-8"))
    receipt = composite_score(parsed, signing_key=load_signing_key(key))
    out.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")


@app.command()
def composite(
    request: _RequestInput,
    key: _SigningKeyInput,
    out: _ReceiptOutput,
) -> None:
    """Score a weighted multi-scale composite and write a signed receipt."""
    try:
        _write_composite(request, key, out)
    except ValidationError as exc:
        _fail_validation(exc, code=InvalidScoreRequest.code)
    except (AssayError, AvowError) as exc:
        _fail(exc)
    except (OSError, ValueError):
        _fail(CliInputInvalid("composite input is unreadable or malformed"))
    typer.echo(f"wrote receipt: {out}")


@app.command()
def verify(
    receipt: _ReceiptInput,
    public_key: _PublicKeyInput,
) -> None:
    """Verify offline against a pinned signer; this does not prove freshness."""
    try:
        parsed = ScoreReceipt.model_validate_json(receipt.read_text(encoding="utf-8"))
        verify_receipt(parsed, expected_public_key=read_public_key(public_key))
    except ValidationError as exc:
        _fail_validation(exc, code=CliInputInvalid.code)
    except AvowError as exc:
        _fail(exc)
    except (OSError, ValueError):
        _fail(CliInputInvalid("verification input is unreadable or malformed"))
    typer.echo("OK: receipt verified")


@app.command()
def verify_ledger(
    public_key: _PublicKeyInput,
    head: _HeadInput,
    ledger: _LedgerInput = None,
) -> None:
    """Verify every ledger entry and link against caller-supplied signer and head pins."""
    ledger_path = ledger if ledger is not None else Path(_load_settings().ledger_path)
    try:
        entries = _ledger_entries(public_key, head, ledger_path)
    except (AssayError, AvowError) as exc:
        _fail(exc)
    except (OSError, ValueError):
        _fail(CliInputInvalid("ledger verification input is unreadable or malformed"))
    noun = "entry" if len(entries) == 1 else "entries"
    typer.echo(f"OK: ledger verified, {len(entries)} {noun} intact")


def _ledger_entries(public_key: Path, head: Path, ledger: Path) -> tuple[ScoreReceipt, ...]:
    return verify_integrity(
        ledger,
        ScoreReceipt,
        expected_public_key=read_public_key(public_key),
        expected_head=read_head(head),
    )
