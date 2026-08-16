"""The base wheel composes scores without loading scientific metric packages."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OPTIONAL_ROOTS = ("numpy", "scipy", "sklearn", "ir_measures", "pydantic_settings")


def _run_with_optional_imports_blocked(code: str) -> subprocess.CompletedProcess[str]:
    program = _import_blocker() + textwrap.dedent(code)
    return subprocess.run(  # noqa: S603 - fixed interpreter, no shell, test-owned code
        [sys.executable, "-c", program],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _import_blocker() -> str:
    roots = repr(frozenset(_OPTIONAL_ROOTS))
    return textwrap.dedent(
        f"""
        import importlib.abc
        import sys

        class OptionalImportBlocker(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.partition(".")[0] in {roots}:
                    raise ModuleNotFoundError("optional dependency blocked")
                return None

        sys.meta_path.insert(0, OptionalImportBlocker())
        """
    )


def test_should_compose_with_every_metrics_dependency_missing() -> None:
    # Given a process where every package in the metrics extra is unavailable
    code = """
        from assay import ClampPolicy, Component, NativeScale, WeightedMeanRequest, compose

        request = WeightedMeanRequest(
            method="weighted_mean",
            method_version="base-wheel-v1",
            components=(
                Component(
                    id="quality",
                    label="Quality",
                    value=8.0,
                    scale=NativeScale(
                        minimum=0.0,
                        maximum=10.0,
                        direction="higher_is_better",
                    ),
                    weight=3.0,
                ),
                Component(
                    id="latency",
                    label="Latency",
                    value=20.0,
                    scale=NativeScale(
                        minimum=0.0,
                        maximum=100.0,
                        direction="lower_is_better",
                    ),
                    weight=1.0,
                ),
            ),
            clamp=ClampPolicy.REJECT,
        )

        result = compose(request)
        assert result.score == 0.8
        assert tuple(row.id for row in result.components) == ("quality", "latency")
    """
    # When the base Assay face is imported and used
    completed = _run_with_optional_imports_blocked(code)
    # Then composition remains fully usable without the metrics extra
    assert completed.returncode == 0, completed.stderr


def test_should_raise_only_stable_redacted_code_when_metrics_extra_is_missing() -> None:
    # Given every optional metric dependency is blocked before an optional face is loaded
    code = """
        from assay.errors import AssayError

        calls = []
        from assay.metrics import binary_scores
        calls.append(lambda: binary_scores([0, 1], [0.1, 0.9]))
        from assay.calibration import calibration_report
        calls.append(lambda: calibration_report([0, 1], [0.1, 0.9], n_bins=2))
        from assay.ranking import precision_at_k
        calls.append(lambda: precision_at_k({"private-doc": 1.0}, ["private-doc"], 1))
        from assay.agreement import percent_agreement
        calls.append(
            lambda: percent_agreement(
                ["private-low"],
                ["private-low"],
                scale=("private-low", "private-high"),
            )
        )
        from assay.uncertainty import mean_interval
        calls.append(
            lambda: mean_interval(
                [1.0],
                min_samples=1,
                n_resamples=9,
                confidence_level=0.9,
                seed=0,
            )
        )
        from assay.settings import AssaySettings
        calls.append(AssaySettings)

        for call in calls:
            try:
                call()
            except AssayError as error:
                assert error.code == "assay.metrics_extra_missing"
                assert str(error) == "assay.metrics_extra_missing"
                assert "private" not in str(error)
                roots = ("numpy", "scipy", "sklearn", "ir_measures", "pydantic_settings")
                assert all(root not in str(error) for root in roots)
            else:
                raise AssertionError("optional metric face unexpectedly ran")
    """
    # When each face is imported and invoked
    completed = _run_with_optional_imports_blocked(code)
    # Then no raw import failure or caller value crosses the boundary
    assert completed.returncode == 0, completed.stderr


def test_should_keep_scientific_and_settings_packages_only_in_metrics_extra() -> None:
    # Given the distribution metadata used to build the wheel
    metadata = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    # When base and metrics requirements are compared
    base = tuple(project["dependencies"])
    metrics = tuple(project["optional-dependencies"]["metrics"])
    # Then the base is only Pydantic and the scientific stack is explicitly optional
    assert base == ("pydantic>=2.11",)
    assert {requirement.partition(">=")[0] for requirement in metrics} == {
        "ir-measures",
        "numpy",
        "pydantic-settings",
        "scikit-learn",
        "scipy",
    }
    assert not any(
        forbidden in requirement.lower()
        for requirement in (*base, *metrics)
        for forbidden in ("avow", "writ", "pynacl", "rfc8785")
    )
