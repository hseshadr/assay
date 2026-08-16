"""Installed-wheel behavior for Assay's scoring-only command line."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from assay import cli

_ROOT = Path(__file__).resolve().parents[1]
_VECTORS = _ROOT / "testdata" / "vectors" / "composition.json"
_EXPECTED_HASH = "sha256:0266b1c59c97bacf85dc945685c55bb4386856b525249c7d5663a8edf020ba06"


@pytest.fixture(scope="module")
def installed_cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Given a real wheel installed with only the command-line extra
    root = tmp_path_factory.mktemp("installed-cli")
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


@pytest.fixture(scope="module")
def installed_full_cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Given a real wheel installed with both command and metric extras
    root = tmp_path_factory.mktemp("installed-full-cli")
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
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(environment / "bin" / "python"),
            f"{wheel}[cli,metrics]",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return environment / "bin" / "assay"


def _northstar_request() -> object:
    vectors = json.loads(_VECTORS.read_text(encoding="utf-8"))
    vector = next(item for item in vectors if item["id"] == "northstar_uncapped_weighted")
    return vector["request"]


def _binary_request() -> dict[str, object]:
    return {
        "metric": "binary",
        "metric_version": "classification.2026-08",
        "y_true": [0, 1, 0, 1],
        "y_score": [0.1, 0.9, 0.4, 0.6],
        "threshold": 0.5,
        "controls": {
            "min_samples": 2,
            "bootstrap_resamples": 19,
            "confidence_level": 0.9,
            "ece_bins": 2,
            "bootstrap_seed": 7,
        },
    }


def _ranking_request() -> dict[str, object]:
    query = lambda name, relevant, ranked: {  # noqa: E731 - compact literal fixture
        "query": name,
        "judgments": [{"doc_id": relevant, "gain": 1}],
        "ranked": ranked,
    }
    return {
        "metric": "ranking",
        "metric_version": "ranking.2026-08",
        "queries": [query("first", "a", ["a", "x"]), query("second", "b", ["y", "b"])],
        "k": 2,
        "controls": {
            "min_samples": 2,
            "bootstrap_resamples": 19,
            "confidence_level": 0.9,
            "bootstrap_seed": 7,
        },
    }


def _agreement_request() -> dict[str, object]:
    return {
        "metric": "agreement",
        "metric_version": "agreement.2026-08",
        "scale": ["low", "middle", "high"],
        "ratings": [
            {"item": "a", "rater_a": "low", "rater_b": "low"},
            {"item": "b", "rater_a": "middle", "rater_b": "high"},
            {"item": "c", "rater_a": "high", "rater_b": "high"},
        ],
        "controls": {
            "min_samples": 2,
            "bootstrap_resamples": 19,
            "confidence_level": 0.9,
            "bootstrap_seed": 7,
        },
    }


def test_should_compose_northstar_request_from_installed_cli(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given the realistic seven-component Northstar request outside the repository
    request = tmp_path / "request.json"
    request.write_text(json.dumps(_northstar_request()), encoding="utf-8")

    # When the installed command composes it
    completed = subprocess.run(
        [str(installed_cli), "compose", "--request", str(request)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then stdout is the complete pinned result and stderr stays empty
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout.endswith("\n")
    assert not completed.stdout.endswith("\n\n")
    result = json.loads(completed.stdout)
    assert result["score"] == 0.92
    assert result["interval"] is None
    assert [row["id"] for row in result["components"]] == [
        "security",
        "privacy",
        "reliability",
        "performance",
        "correctness",
        "clarity",
        "production",
    ]
    assert result["inputs_hash"] == _EXPECTED_HASH


def test_should_fail_with_metrics_extra_code_after_cli_only_parse(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given a valid measurement request and an installed CLI without metric dependencies
    request = tmp_path / "binary.json"
    request.write_text(json.dumps(_binary_request()), encoding="utf-8")

    # When the command parses and attempts execution
    completed = subprocess.run(
        [str(installed_cli), "measure", "--request", str(request)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then the optional boundary, not parsing or import internals, is visible
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "FAIL: assay.metrics_extra_missing\n"


def test_should_measure_binary_family_from_installed_full_cli(
    installed_full_cli: Path, tmp_path: Path
) -> None:
    # Given the same request and a wheel carrying both required extras
    request = tmp_path / "binary.json"
    request.write_text(json.dumps(_binary_request()), encoding="utf-8")

    # When the installed measurement command executes
    completed = subprocess.run(
        [str(installed_full_cli), "measure", "--request", str(request)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then the family-specific report is serialized without a universal score
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["schema"] == "assay.measurement/v1"
    assert payload["metric"] == "binary"
    assert set(payload["report"]) == {"classification", "calibration", "accuracy_interval"}
    assert "score" not in payload


@pytest.mark.parametrize(
    ("request_payload", "metric", "report_key"),
    [
        (_ranking_request(), "ranking", "ndcg_interval"),
        (_agreement_request(), "agreement", "weighted_agreement_interval"),
    ],
)
def test_should_measure_each_nonbinary_family_from_installed_full_cli(
    installed_full_cli: Path,
    tmp_path: Path,
    request_payload: dict[str, object],
    metric: str,
    report_key: str,
) -> None:
    # Given a complete ranking or agreement request
    request = tmp_path / f"{metric}.json"
    request.write_text(json.dumps(request_payload), encoding="utf-8")

    # When the installed full command measures it
    completed = subprocess.run(
        [str(installed_full_cli), "measure", "--request", str(request)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then its native report shape and interval survive serialization
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["metric"] == metric
    assert report_key in payload["report"]
    assert "score" not in payload


def test_should_replay_and_explain_serialized_score_result(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given a real serialized Northstar result produced by the installed command
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(json.dumps(_northstar_request()), encoding="utf-8")
    composed = subprocess.run(
        [str(installed_cli), "compose", "--request", str(request)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    result.write_text(composed.stdout, encoding="utf-8")

    # When the installed command validates and explains that result
    completed = subprocess.run(
        [str(installed_cli), "explain", "--result", str(result)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then deterministic arithmetic is readable in original component order
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout == (
        "Assay score explanation\n"
        "Method: weighted_mean@northstar.2026-08-12\n"
        "Score: 0.92\n"
        "Interval: deterministic\n"
        "Components:\n"
        "1. security: raw=19.0; normalized=0.95; operation=add; coefficient=0.2; "
        "contribution=0.19\n"
        "2. privacy: raw=15.0; normalized=1.0; operation=add; coefficient=0.15; contribution=0.15\n"
        "3. reliability: raw=15.0; normalized=1.0; operation=add; coefficient=0.15; "
        "contribution=0.15\n"
        "4. performance: raw=12.0; normalized=0.8; operation=add; coefficient=0.15; "
        "contribution=0.12\n"
        "5. correctness: raw=15.0; normalized=1.0; operation=add; coefficient=0.15; "
        "contribution=0.15\n"
        "6. clarity: raw=14.0; normalized=0.9333333333333333; operation=add; "
        "coefficient=0.15; contribution=0.13999999999999999\n"
        "7. production: raw=2.0; normalized=0.4; operation=add; coefficient=0.05; "
        "contribution=0.020000000000000004\n"
    )


def test_should_mark_selected_component_in_minimum_explanation(
    installed_cli: Path, tmp_path: Path
) -> None:
    # Given a minimum request whose first component is the declared bottleneck
    scale = {"minimum": 0, "maximum": 10, "direction": "higher_is_better"}
    request = tmp_path / "minimum.json"
    result = tmp_path / "minimum-result.json"
    request.write_text(
        json.dumps(
            {
                "method": "minimum",
                "method_version": "bottleneck.v1",
                "components": [
                    {"id": "first", "label": "First", "value": 2, "scale": scale},
                    {"id": "second", "label": "Second", "value": 8, "scale": scale},
                ],
                "clamp": "reject",
            }
        ),
        encoding="utf-8",
    )
    composed = _invoke_cli(installed_cli, tmp_path, "compose", "--request", str(request))
    result.write_text(composed.stdout, encoding="utf-8")

    # When the result is explained
    explained = _invoke_cli(installed_cli, tmp_path, "explain", "--result", str(result))

    # Then every row names whether it was selected
    assert explained.returncode == 0, explained.stderr
    assert "1. first:" in explained.stdout
    assert "contribution=0.2; selected=yes" in explained.stdout
    assert "2. second:" in explained.stdout
    assert "contribution=0.8; selected=no" in explained.stdout


def _invoke_cli(cli: Path, cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(cli), *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_should_dispatch_compose_through_in_process_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    # Given a valid request passed through the installed console function
    request = tmp_path / "request.json"
    request.write_text(json.dumps(_northstar_request()), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["assay", "compose", "--request", str(request)])

    # When the dependency-light entrypoint dispatches to Typer
    status = cli.main()
    captured = capfd.readouterr()

    # Then the same complete result reaches stdout
    assert status == 0
    assert captured.err == ""
    assert json.loads(captured.out)["score"] == 0.92


def test_should_dispatch_measure_through_in_process_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    # Given a complete binary request
    request = tmp_path / "binary.json"
    request.write_text(json.dumps(_binary_request()), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["assay", "measure", "--request", str(request)])

    # When it executes through the public console function
    status = cli.main()
    captured = capfd.readouterr()

    # Then its typed family report is written
    assert status == 0
    assert captured.err == ""
    assert json.loads(captured.out)["metric"] == "binary"


def test_should_dispatch_explain_through_in_process_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    # Given a result created through the same public console function
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(json.dumps(_northstar_request()), encoding="utf-8")
    compose_args = ["assay", "compose", "--request", str(request), "--out", str(result)]
    monkeypatch.setattr("sys.argv", compose_args)
    assert cli.main() == 0
    capfd.readouterr()
    monkeypatch.setattr("sys.argv", ["assay", "explain", "--result", str(result)])

    # When it is replayed in process
    status = cli.main()
    captured = capfd.readouterr()

    # Then the deterministic explanation reaches stdout
    assert status == 0
    assert captured.err == ""
    assert captured.out.startswith("Assay score explanation\nMethod: weighted_mean@")


def test_should_translate_in_process_parser_failure_to_static_code(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    # Given a private unknown command
    monkeypatch.setattr("sys.argv", ["assay", "PRIVATE_COMMAND"])

    # When the console parser refuses it
    status = cli.main()
    captured = capfd.readouterr()

    # Then the entrypoint translates the parser error without usage rendering
    assert status == 2
    assert captured.out == ""
    assert captured.err == "FAIL: assay.cli_input_invalid\n"
