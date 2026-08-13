"""Executable checks for the documented privacy and performance boundary."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

from nacl.signing import SigningKey

from assay.api import score, verify
from assay.models import ScoreRequest
from assay.settings import AssaySettings

_SEED = bytes(range(32))


def _request() -> ScoreRequest:
    return ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=[0, 1] * 20,
        y_score=[0.2, 0.8] * 20,
    )


def test_python_api_has_no_network_or_hidden_persistence(
    tmp_path: Path, monkeypatch: object
) -> None:
    # Given every attempt to open a runtime socket is a test failure
    def refuse_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("runtime egress attempted")

    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(socket, "socket", refuse_socket)  # type: ignore[attr-defined]
    # When a representative score is signed and verified
    key = SigningKey(_SEED)
    receipt = score(_request(), signing_key=key, settings=AssaySettings())
    # Then it verifies locally and creates no implicit file or cache
    assert verify(receipt, expected_public_key=bytes(key.verify_key).hex())
    assert tuple(tmp_path.iterdir()) == ()


def test_operations_doc_freezes_every_release_acceptance_number() -> None:
    contract = Path("docs/OPERATIONS.md").read_text(encoding="utf-8")

    assert "No network, DNS, telemetry, subprocess, or background thread" in contract
    assert "not encryption" in contract
    assert "Default timeout: **5.0 seconds**" in contract
    assert "64 MiB, 100,000 entries, or one 64 KiB encoded line" in contract
    assert "prebuilt 5,000-entry history" in contract
    assert "one empty same-volume probe directory" in contract
    assert "blank lines, CRLF, and a partial final line are malformed" in contract
    assert "**RPO 0**" in contract
    assert "p50 <= **2 ms**, p95 <= **4 ms**, p99 <= **10 ms**" in contract
    assert "p50 <= **3 ms**, p95 <= **8 ms**, p99 <= **20 ms**" in contract
    assert "p50 <= **75 ms**, p95 <= **150 ms**, p99 <= **300 ms**" in contract
    assert "timed append plus verify <= **15 s**" in contract
    assert "uv run poe benchmark" in contract
    assert "pnpm --dir ts benchmark" in contract


def test_typescript_runtime_has_no_egress_or_persistence_primitive() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in Path("ts/src").glob("*.ts"))
    forbidden = ("fetch(", "XMLHttpRequest", "sendBeacon", "localStorage", "indexedDB", "WebSocket")

    assert all(primitive not in sources for primitive in forbidden)


def test_frozen_benchmarks_are_wired_into_local_and_ci_gates() -> None:
    project = Path("pyproject.toml").read_text(encoding="utf-8")
    package = Path("ts/package.json").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert Path("src/avow/benchmarks/release.py").is_file()
    assert Path("ts/benchmarks/release.mjs").is_file()
    assert 'benchmark = "python -m avow.benchmarks.release"' in project
    assert '"benchmark": "tsc -p tsconfig.build.json && node benchmarks/release.mjs"' in package
    assert "uv run poe benchmark" in workflow
    assert "pnpm benchmark" in workflow


def test_typescript_benchmark_measures_peak_not_current_rss() -> None:
    # Given the contract budgets peak resident memory, not one end-of-run snapshot
    source = Path("ts/benchmarks/release.mjs").read_text(encoding="utf-8")
    # Then the shipped benchmark reads Node's high-water mark directly
    assert "process.resourceUsage().maxRSS" in source
    assert "process.memoryUsage().rss" not in source


def test_shipped_python_benchmarks_meet_the_frozen_contract() -> None:
    # Given the exact workloads shipped in the wheel
    # When every workload enforces its own frozen latency, RSS, and integrity budget
    command = [sys.executable, "-m", "avow.benchmarks.release"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    report = json.loads(result.stdout)
    # Then all complete with the predeclared operation counts
    assert tuple(report[name]["count"] for name in ("envelope", "classification", "ledger")) == (
        500,
        100,
        200,
    )
