"""Privacy and crash-safe filesystem boundaries for the Assay CLI."""

from __future__ import annotations

import json
import os
import subprocess
import unicodedata
from pathlib import Path

import pytest

from assay import _cli_io
from assay.errors import CliInputInvalid, CliOutputInvalid

_ROOT = Path(__file__).resolve().parents[1]
_VECTORS = _ROOT / "testdata" / "vectors" / "composition.json"


@pytest.fixture(scope="module")
def installed_cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Given a real wheel installed with the command extra
    root = tmp_path_factory.mktemp("privacy-cli")
    artifacts = root / "artifacts"
    environment = root / "environment"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(artifacts)],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(artifacts.glob("*.whl"))
    subprocess.run(
        ["uv", "venv", "--python", "3.13", str(environment)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["uv", "pip", "install", "--python", str(environment / "bin" / "python"), f"{wheel}[cli]"],
        check=True,
        capture_output=True,
        text=True,
    )
    return environment / "bin" / "assay"


def _request_payload() -> str:
    vectors = json.loads(_VECTORS.read_text(encoding="utf-8"))
    vector = next(item for item in vectors if item["id"] == "northstar_uncapped_weighted")
    return json.dumps(vector["request"])


def _invoke(cli: Path, cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(cli), *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_should_install_exact_stdout_bytes_atomically_without_path_echo(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given the same valid request for stdout and file output
    request = tmp_path / "request.json"
    output = tmp_path / "result.json"
    request.write_text(_request_payload(), encoding="utf-8")
    streamed = _invoke(installed_cli, tmp_path, "compose", "--request", str(request))

    # When output is directed to a file
    installed = _invoke(
        installed_cli,
        tmp_path,
        "compose",
        "--request",
        str(request),
        "--out",
        str(output),
    )

    # Then exact serialized bytes are atomically installed and no path is emitted
    assert streamed.returncode == 0
    assert installed.returncode == 0, installed.stderr
    assert installed.stdout == ""
    assert installed.stderr == ""
    assert output.read_bytes() == streamed.stdout.encode()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["request.json", "result.json"]


def test_should_leave_complete_old_output_and_no_stage_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given an old result and a failure injected at the atomic replacement boundary
    source = tmp_path / "request.json"
    output = tmp_path / "result.json"
    source.write_bytes(b"request")
    output.write_bytes(b"old-complete\n")
    calls = 0

    def fail_replace(_source: str | bytes, _destination: str | bytes) -> None:
        nonlocal calls
        calls += 1
        raise OSError

    monkeypatch.setattr(_cli_io.os, "replace", fail_replace)

    # When the new complete payload cannot be installed
    with pytest.raises(CliOutputInvalid, match=r"^assay\.cli_output_invalid$"):
        _cli_io.write_output(b"new-complete\n", str(output), str(source))

    # Then replace was attempted once, the old result survived, and staging was removed
    assert calls == 1
    assert output.read_bytes() == b"old-complete\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["request.json", "result.json"]


@pytest.mark.parametrize(
    "alias_kind", ["exact", "parent", "symlink", "hardlink", "case", "unicode"]
)
def test_should_reject_every_input_output_alias_without_mutation(
    installed_cli: Path, tmp_path: Path, alias_kind: str
) -> None:
    # Given one request referenced through an exact, filesystem, or normalized alias
    source = tmp_path / ("Café.json" if alias_kind in {"case", "unicode"} else "request.json")
    source.write_text(_request_payload(), encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    aliases = {
        "exact": source,
        "parent": child / ".." / source.name,
        "symlink": tmp_path / "request-link.json",
        "hardlink": tmp_path / "request-hard.json",
        "case": tmp_path / "café.json",
        "unicode": tmp_path / unicodedata.normalize("NFD", source.name),
    }
    output = aliases[alias_kind]
    if alias_kind == "symlink":
        output.symlink_to(source)
    if alias_kind == "hardlink":
        os.link(source, output)
    original = source.read_bytes()

    # When composition tries to replace the request through that alias
    completed = _invoke(
        installed_cli,
        tmp_path,
        "compose",
        "--request",
        str(source),
        "--out",
        str(output),
    )

    # Then the value-free output code is returned and the request stays complete
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "FAIL: assay.cli_output_invalid\n"
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "arguments",
    [
        ("PRIVATE_COMMAND",),
        ("compose", "--PRIVATE_OPTION", "PRIVATE_SENTINEL"),
        ("compose",),
    ],
)
def test_should_redact_parser_tokens_and_usage(
    installed_cli: Path, tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    # Given an unknown command, option, or missing required option
    # When it reaches the parser boundary
    completed = _invoke(installed_cli, tmp_path, *arguments)

    # Then Typer usage and caller-controlled tokens never escape
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "FAIL: assay.cli_input_invalid\n"
    assert "Usage" not in completed.stderr
    assert "PRIVATE" not in completed.stderr


@pytest.mark.parametrize("payload", [b'{"private":"PRIVATE_SENTINEL"', b"\xffPRIVATE_SENTINEL"])
def test_should_redact_malformed_json_and_utf8(
    installed_cli: Path, tmp_path: Path, payload: bytes
) -> None:
    # Given malformed caller bytes containing a private sentinel
    request = tmp_path / "PRIVATE_PATH.json"
    request.write_bytes(payload)

    # When composition reads them
    completed = _invoke(installed_cli, tmp_path, "compose", "--request", str(request))

    # Then only a stable contract code is visible
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "FAIL: assay.invalid_contract\n"
    assert "PRIVATE" not in completed.stderr
    assert "Traceback" not in completed.stderr


def test_should_redact_finite_integer_overflow_from_installed_cli(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given valid sub-megabyte measurement JSON containing a private 1,000-digit integer
    huge = "9" * 1_000
    request = tmp_path / "PRIVATE_OVERFLOW.json"
    request.write_text(
        '{"metric":"binary","metric_version":"classification.2026-08",'
        f'"y_true":[0,1],"y_score":[0.1,{huge}]}}',
        encoding="utf-8",
    )

    # When the real CLI-only wheel parses the family contract
    completed = _invoke(installed_cli, tmp_path, "measure", "--request", str(request))

    # Then no numeric value, exception context, or traceback crosses the CLI boundary
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "FAIL: assay.invalid_request\n"
    assert "PRIVATE" not in completed.stderr
    assert "OverflowError" not in completed.stderr
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            '{"metric":"ranking","metric_version":"ranking.2026-08",'
            '"queries":[{"query":"q","judgments":[{"doc_id":"a","gain":HUGE}],'
            '"ranked":["a"]}]}',
            "assay.invalid_ranking_request",
        ),
        (
            '{"metric":"binary","metric_version":"classification.2026-08",'
            '"y_true":[0,1],"y_score":[0.1,0.9],"controls":{"confidence_level":HUGE}}',
            "assay.invalid_settings",
        ),
        (
            '{"metric":"ranking","metric_version":"ranking.2026-08",'
            '"queries":[{"query":"q","judgments":[{"doc_id":"a","gain":1}],'
            '"ranked":["a"]}],"controls":{"confidence_level":HUGE}}',
            "assay.invalid_settings",
        ),
        (
            '{"metric":"agreement","metric_version":"agreement.2026-08",'
            '"scale":["low","high"],"ratings":'
            '[{"item":"a","rater_a":"low","rater_b":"high"}],'
            '"controls":{"confidence_level":HUGE}}',
            "assay.invalid_settings",
        ),
    ],
    ids=["ranking-gain", "binary-confidence", "ranking-confidence", "agreement-confidence"],
)
def test_should_redact_family_numeric_overflow_from_installed_cli(
    installed_cli: Path, tmp_path: Path, payload: str, code: str
) -> None:
    # Given one valid sub-megabyte family wire containing a 1,000-digit integer
    huge = "9" * 1_000
    request = tmp_path / "PRIVATE_FAMILY_OVERFLOW.json"
    request.write_text(payload.replace("HUGE", huge), encoding="utf-8")

    # When the real CLI-only wheel parses the request
    completed = _invoke(installed_cli, tmp_path, "measure", "--request", str(request))

    # Then it returns the intended family code without values or exception context
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == f"FAIL: {code}\n"
    assert huge not in completed.stderr
    assert "OverflowError" not in completed.stderr
    assert "Traceback" not in completed.stderr


def test_should_reject_duplicate_json_members_from_every_installed_command(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given duplicate-bearing composition, measurement, and result wires
    compose_request = tmp_path / "PRIVATE_COMPOSE.json"
    measure_request = tmp_path / "PRIVATE_MEASURE.json"
    result = tmp_path / "PRIVATE_RESULT.json"
    compose_payload = _request_payload().replace(
        '"method": "weighted_mean"', '"method":"PRIVATE_FIRST","method":"weighted_mean"', 1
    )
    measure_payload = (
        '{"metric":"PRIVATE_FIRST","metric":"binary",'
        '"metric_version":"classification.2026-08","y_true":[0,1],"y_score":[0.1,0.9]}'
    )
    valid_request = tmp_path / "valid-request.json"
    valid_request.write_text(_request_payload(), encoding="utf-8")
    composed = _invoke(installed_cli, tmp_path, "compose", "--request", str(valid_request))
    duplicate_result = composed.stdout.replace('"score":', '"score":0.0,"score":', 1)
    compose_request.write_text(compose_payload, encoding="utf-8")
    measure_request.write_text(measure_payload, encoding="utf-8")
    result.write_text(duplicate_result, encoding="utf-8")

    # When each installed command parses its public JSON boundary
    completed = (
        _invoke(installed_cli, tmp_path, "compose", "--request", str(compose_request)),
        _invoke(installed_cli, tmp_path, "measure", "--request", str(measure_request)),
        _invoke(installed_cli, tmp_path, "explain", "--result", str(result)),
    )

    # Then all reject before last-wins collapse with one redacted deterministic code
    assert all(call.returncode == 2 for call in completed)
    assert all(call.stdout == "" for call in completed)
    assert all(call.stderr == "FAIL: assay.duplicate_field\n" for call in completed)
    assert all("PRIVATE" not in call.stderr for call in completed)
    assert all("Traceback" not in call.stderr for call in completed)


def test_should_reject_oversized_or_nonregular_input_without_path_echo(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given one oversized file and one directory in place of a regular request
    oversized = tmp_path / "PRIVATE_OVERSIZED.json"
    oversized.write_bytes(b"x" * 1_048_577)
    directory = tmp_path / "PRIVATE_DIRECTORY"
    directory.mkdir()

    # When each unsafe input is read
    results = (
        _invoke(installed_cli, tmp_path, "compose", "--request", str(oversized)),
        _invoke(installed_cli, tmp_path, "compose", "--request", str(directory)),
    )

    # Then both fail with the same value-free input code
    assert all(result.returncode == 2 for result in results)
    assert all(result.stdout == "" for result in results)
    assert all(result.stderr == "FAIL: assay.cli_input_invalid\n" for result in results)


def test_should_reject_fifo_input_without_blocking_or_writing(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given a real FIFO with no writer and a private destination
    request = tmp_path / "PRIVATE_FIFO"
    output = tmp_path / "PRIVATE_OUTPUT.json"
    os.mkfifo(request)

    # When the installed command opens the non-regular input
    try:
        completed = subprocess.run(
            [
                str(installed_cli),
                "compose",
                "--request",
                str(request),
                "--out",
                str(output),
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("CLI blocked while opening a FIFO input")

    # Then it fails immediately with no path leak or output mutation
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "FAIL: assay.cli_input_invalid\n"
    assert "PRIVATE" not in completed.stderr
    assert not output.exists()


def test_should_reject_tampered_result_without_echoing_private_fields(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given a valid result whose arithmetic and shape were both tampered
    request = tmp_path / "request.json"
    result = tmp_path / "PRIVATE_RESULT.json"
    request.write_text(_request_payload(), encoding="utf-8")
    composed = _invoke(installed_cli, tmp_path, "compose", "--request", str(request))
    payload = json.loads(composed.stdout)
    payload["score"] = 0.01
    payload["PRIVATE_SENTINEL"] = "PRIVATE_SENTINEL"
    result.write_text(json.dumps(payload), encoding="utf-8")

    # When replay validation runs
    completed = _invoke(installed_cli, tmp_path, "explain", "--result", str(result))

    # Then neither Pydantic context nor private values cross the boundary
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr.startswith("FAIL: assay.")
    assert "PRIVATE" not in completed.stderr
    assert "input_value" not in completed.stderr
    assert "Traceback" not in completed.stderr


def test_should_read_regular_input_and_reject_missing_directory_and_oversize(
    tmp_path: Path,
) -> None:
    # Given a small file, a missing path, a directory, and an oversized file
    regular = tmp_path / "regular.json"
    regular.write_bytes(b"{}")
    missing = tmp_path / "missing.json"
    directory = tmp_path / "directory"
    directory.mkdir()
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * 1_048_577)

    # When / Then only the bounded regular file can be read
    assert _cli_io.read_input(str(regular)) == b"{}"
    for unsafe in (missing, directory, oversized):
        with pytest.raises(CliInputInvalid, match=r"^assay\.cli_input_invalid$"):
            _cli_io.read_input(str(unsafe))


def test_should_atomically_replace_existing_output_and_flush_parent(tmp_path: Path) -> None:
    # Given a distinct source and an old destination
    source = tmp_path / "request.json"
    output = tmp_path / "result.json"
    source.write_bytes(b"request")
    output.write_bytes(b"old\n")

    # When exact new bytes are installed directly through the IO boundary
    _cli_io.write_output(b"new\n", str(output), str(source))

    # Then replacement is complete and no stage remains
    assert output.read_bytes() == b"new\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["request.json", "result.json"]


@pytest.mark.parametrize("unsafe_kind", ["symlink", "directory", "missing-parent"])
def test_should_reject_unsafe_output_types_directly(tmp_path: Path, unsafe_kind: str) -> None:
    # Given a source and an unsafe output destination
    source = tmp_path / "request.json"
    source.write_bytes(b"request")
    output = tmp_path / "output"
    if unsafe_kind == "symlink":
        target = tmp_path / "target.json"
        target.write_bytes(b"old")
        output.symlink_to(target)
    elif unsafe_kind == "directory":
        output.mkdir()
    else:
        output = tmp_path / "missing" / "output.json"

    # When / Then the destination is refused without mutation
    with pytest.raises(CliOutputInvalid, match=r"^assay\.cli_output_invalid$"):
        _cli_io.write_output(b"new", str(output), str(source))
