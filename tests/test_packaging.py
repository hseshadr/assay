"""The distribution is named ``avow``, ships three import packages, and keeps the
heavy scoring stack behind the ``[assay]`` extra so the base install (and Pyodide /
micropip) never pulls scikit-learn."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import avow


def _cfg() -> dict[str, object]:
    return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))


def test_dist_is_avow_with_three_packages_and_extras() -> None:
    cfg = _cfg()
    project = cfg["project"]
    assert isinstance(project, dict)
    assert project["name"] == "avow"

    hatch = cfg["tool"]["hatch"]  # type: ignore[index]
    packages = hatch["build"]["targets"]["wheel"]["packages"]
    assert set(packages) == {"src/avow", "src/assay", "src/writ"}

    base = " ".join(project["dependencies"])  # type: ignore[arg-type]
    assert "scikit-learn" not in base
    assert "scipy" not in base
    assert "numpy" not in base
    assert "pynacl" in base
    assert "rfc8785" in base
    assert "pydantic" in base

    extras = project["optional-dependencies"]  # type: ignore[index]
    assert any("scikit-learn" in d for d in extras["assay"])
    assert any("scipy" in d for d in extras["assay"])
    assert any("numpy" in d for d in extras["assay"])
    assert any("typer" in d for d in extras["cli"])


def test_base_dependencies_carry_no_cli_dep() -> None:
    project = _cfg()["project"]
    assert isinstance(project, dict)
    base = " ".join(project["dependencies"])
    assert "typer" not in base


def test_python_and_typescript_packages_carry_the_same_version() -> None:
    # Given one `v*` tag that fans out to BOTH registries (see .github/workflows/publish.yml)
    ts_version = json.loads(Path("ts/package.json").read_text(encoding="utf-8"))["version"]
    # Then the two must agree: bumping only one would push an already-published version
    # to the other registry, which npm and PyPI both reject — a release that fails at the
    # very last step, long after the tag is public.
    assert ts_version == avow.__version__


def test_release_artifacts_ship_the_exact_benchmark_and_operational_contract() -> None:
    cfg = _cfg()
    only_include = cfg["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]  # type: ignore[index]
    package = json.loads(Path("ts/package.json").read_text(encoding="utf-8"))

    assert Path("src/avow/benchmarks/release.py").is_file()
    assert "docs" in only_include
    assert "benchmarks" in package["files"]
