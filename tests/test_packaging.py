"""The distribution is named ``avow``, ships three import packages, and keeps the
heavy scoring stack behind the ``[assay]`` extra so the base install (and Pyodide /
micropip) never pulls scikit-learn."""

from __future__ import annotations

import tomllib
from pathlib import Path


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
