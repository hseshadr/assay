"""Typer-backed scoring commands, loaded only after migration dispatch."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from pydantic import ValidationError
from typer._click.exceptions import ClickException

from assay._cli_io import json_bytes, read_input, write_output
from assay.compose import compose
from assay.contracts import ExplainedComponent, Interval, ScoreResult, parse_request_json
from assay.errors import CliInputInvalid
from assay.measurement import measure, parse_measurement_json

app = typer.Typer(add_completion=False, no_args_is_help=False, pretty_exceptions_enable=False)


@app.callback()
def root() -> None:
    """Combine or inspect typed measurements."""


@app.command("compose")
def compose_command(
    request: Annotated[str, typer.Option("--request")],
    out: Annotated[str | None, typer.Option("--out")] = None,
) -> None:
    """Compose one validated scoring request."""
    source = read_input(request)
    result = compose(parse_request_json(source))
    write_output(json_bytes(result), out, request)


@app.command("measure")
def measure_command(
    request: Annotated[str, typer.Option("--request")],
    out: Annotated[str | None, typer.Option("--out")] = None,
) -> None:
    """Run one typed optional measurement family."""
    source = read_input(request)
    result = measure(parse_measurement_json(source))
    write_output(json_bytes(result), out, request)


def _number(value: float | None) -> str:
    return "none" if value is None else json.dumps(value, allow_nan=False)


def _interval(interval: Interval | None) -> str:
    if interval is None:
        return "deterministic"
    return f"[{_number(interval.low)}, {_number(interval.high)}]"


def _selection(component: ExplainedComponent, selected: str | None) -> str:
    if selected is None:
        return ""
    return f"; selected={'yes' if component.id == selected else 'no'}"


def _component_line(index: int, row: ExplainedComponent, selected: str | None) -> str:
    values = (
        f"raw={_number(row.raw)}; normalized={_number(row.normalized)}",
        f"operation={row.operation}; coefficient={_number(row.coefficient)}",
        f"contribution={_number(row.contribution)}{_selection(row, selected)}",
    )
    return f"{index}. {row.id}: {'; '.join(values)}"


def _explanation(result: ScoreResult) -> str:
    lines = [
        "Assay score explanation",
        f"Method: {result.method.id}@{result.method.version}",
        f"Score: {_number(result.score)}",
        f"Interval: {_interval(result.interval)}",
        "Components:",
    ]
    rows = enumerate(result.components, start=1)
    lines.extend(_component_line(index, row, result.selected_component_id) for index, row in rows)
    return "\n".join(lines) + "\n"


@app.command("explain")
def explain_command(
    result: Annotated[str, typer.Option("--result")],
    out: Annotated[str | None, typer.Option("--out")] = None,
) -> None:
    """Replay result invariants and render deterministic arithmetic."""
    validated = ScoreResult.model_validate_json(read_input(result))
    write_output(_explanation(validated).encode("utf-8"), out, result)


def run(arguments: tuple[str, ...]) -> int:
    """Run Typer without allowing its usage rendering to cross the boundary."""
    try:
        app(args=list(arguments), standalone_mode=False)
    except (ClickException, SystemExit, ValidationError, RecursionError):
        raise CliInputInvalid from None
    return 0
