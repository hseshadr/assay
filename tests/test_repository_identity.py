"""Executable repository identity and import-boundary contracts."""

from __future__ import annotations

import ast
import importlib
import runpy
import sys
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).parents[1]
FORBIDDEN_IMPORT_ROOTS = frozenset({"avow", "writ", "nacl", "rfc8785"})


def _load_pyproject() -> Mapping[str, object]:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return cast(Mapping[str, object], tomllib.loads(pyproject))


def _table(config: Mapping[str, object], *keys: str) -> Mapping[str, object]:
    current = config
    for key in keys:
        value = current[key]
        assert isinstance(value, dict)
        current = cast(Mapping[str, object], value)
    return current


def _import_roots(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    direct = {
        alias.name.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    from_imports = {
        node.module.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    return frozenset(direct | from_imports)


def _console_main() -> Callable[[], int]:
    scripts = _table(_load_pyproject(), "project", "scripts")
    entry = scripts["assay"]
    assert isinstance(entry, str)
    module_name, separator, attribute = entry.partition(":")
    assert separator
    module = importlib.import_module(module_name)
    return cast(Callable[[], int], getattr(module, attribute))


def test_should_name_scoring_distribution_assay_engine() -> None:
    # Given
    project = _table(_load_pyproject(), "project")

    # When
    distribution_name = project["name"]

    # Then
    assert distribution_name == "assay-engine"


def test_should_package_only_assay_when_building_wheel() -> None:
    # Given
    project = _load_pyproject()

    # When
    wheel = _table(project, "tool", "hatch", "build", "targets", "wheel")

    # Then
    assert wheel["packages"] == ["src/assay"]


def test_should_single_source_assay_development_version() -> None:
    # Given
    project = _load_pyproject()
    expected_path = "src/assay/_version.py"

    # When
    version_config = _table(project, "tool", "hatch", "version")

    # Then
    assert version_config["path"] == expected_path
    assert (ROOT / expected_path).is_file()
    version_module = runpy.run_path(ROOT / expected_path)
    assert version_module["__version__"] == "0.5.0.dev0"


def test_should_install_assay_console_script() -> None:
    # Given
    project = _load_pyproject()

    # When
    scripts = _table(project, "project", "scripts")

    # Then
    assert scripts["assay"] == "assay.cli:main"


def test_should_import_assay_console_entry() -> None:
    # Given / When
    main = _console_main()

    # Then
    assert callable(main)


def test_should_refuse_legacy_security_command_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given
    private_key = tmp_path / "legacy.key"
    public_key = tmp_path / "legacy.pub"
    command = ["assay", "keygen", "--out", str(private_key), "--pub", str(public_key)]
    monkeypatch.setattr(sys, "argv", command)

    # When
    status = _console_main()()
    captured = capsys.readouterr()

    # Then
    assert status == 1
    assert "assay.scoring_core_pending" in captured.err
    assert not private_key.exists()
    assert not public_key.exists()


def test_should_exclude_other_product_source_packages() -> None:
    # Given
    other_products = (ROOT / "src" / "avow", ROOT / "src" / "writ")

    # When
    existing_products = [path for path in other_products if path.exists()]

    # Then
    assert not existing_products


def test_should_reject_cross_product_imports_from_assay() -> None:
    # Given
    sources = sorted((ROOT / "src" / "assay").rglob("*.py"))

    # When
    violations = [
        (str(path.relative_to(ROOT)), sorted(_import_roots(path) & FORBIDDEN_IMPORT_ROOTS))
        for path in sources
        if _import_roots(path) & FORBIDDEN_IMPORT_ROOTS
    ]

    # Then
    assert not violations, violations
