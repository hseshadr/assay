"""Fail-closed migration boundary for every historical Assay command."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_EXIT_USAGE = 2
_MIGRATIONS = (
    (
        "keygen",
        "FAIL: assay.command_moved_to_avow; use `avow keygen ...`\n",
    ),
    (
        "sign",
        "FAIL: assay.command_moved_to_avow; use `avow sign ...`\n",
    ),
    (
        "verify",
        "FAIL: assay.command_moved_to_avow; use `avow verify ...`\n",
    ),
    (
        "verify-ledger",
        "FAIL: assay.command_moved_to_avow; use `avow ledger verify ...`\n",
    ),
    (
        "score",
        "FAIL: assay.command_replaced; use `assay measure ...`\n",
    ),
    (
        "composite",
        "FAIL: assay.command_replaced; use `assay compose ...`\n",
    ),
)


@pytest.fixture(scope="module")
def installed_base_cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Given a real base wheel with no command or metric extras
    root = tmp_path_factory.mktemp("installed-base-cli")
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
        ["uv", "pip", "install", "--python", str(environment / "bin" / "python"), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    return environment / "bin" / "assay"


def _guarded_environment(tmp_path: Path) -> dict[str, str]:
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        """
import builtins
import socket
import subprocess

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "typer" or name.startswith("assay._cli_app"):
        raise RuntimeError("forbidden late dispatch")
    return original_import(name, *args, **kwargs)

def explode(*args, **kwargs):
    raise RuntimeError("forbidden side effect")

builtins.__import__ = guarded_import
socket.socket = explode
subprocess.Popen = explode
""".lstrip(),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


@pytest.mark.parametrize(("command", "expected"), _MIGRATIONS)
def test_should_refuse_historical_command_without_echo_or_mutation(
    installed_base_cli: Path,
    tmp_path: Path,
    command: str,
    expected: str,
) -> None:
    # Given private trailing values, fake executables, and exploding late dispatch
    fake = tmp_path / "avow"
    fake.write_text("#!/bin/sh\ntouch executed\n", encoding="utf-8")
    fake.chmod(0o755)
    environment = _guarded_environment(tmp_path)
    environment["PATH"] = f"{tmp_path}{os.pathsep}{environment['PATH']}"
    before = {path.name for path in tmp_path.iterdir()}

    # When a historical command is invoked from the base wheel
    completed = subprocess.run(
        [str(installed_base_cli), command, "--out", "PRIVATE_SENTINEL", "https://private.invalid"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then only the static migration boundary runs
    assert completed.returncode == _EXIT_USAGE
    assert completed.stdout == ""
    assert completed.stderr == expected
    assert "PRIVATE_SENTINEL" not in completed.stderr
    assert "private.invalid" not in completed.stderr
    assert {path.name for path in tmp_path.iterdir()} == before
    assert not (tmp_path / "executed").exists()


def test_should_fail_cleanly_when_new_command_runs_without_cli_extra(
    installed_base_cli: Path, tmp_path: Path
) -> None:
    # Given a base wheel with no Typer dependency and a private request path
    request = tmp_path / "PRIVATE_SENTINEL.json"

    # When a current command is invoked
    completed = subprocess.run(
        [str(installed_base_cli), "compose", "--request", str(request)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then the missing optional dependency is code-only and no file is touched
    assert completed.returncode == _EXIT_USAGE
    assert completed.stdout == ""
    assert completed.stderr == "FAIL: assay.cli_extra_missing\n"
    assert "PRIVATE_SENTINEL" not in completed.stderr
    assert not request.exists()
