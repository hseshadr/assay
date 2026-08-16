"""Typed three-family measurement contract and execution."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from assay import (
    AgreementMeasurementRequest,
    BinaryMeasurementRequest,
    BinaryMetricControls,
    OrdinalRating,
    RankingMeasurementRequest,
    RankingMetricControls,
    RankingQueryInput,
    RelevanceInput,
    UncertaintyControls,
    measure,
    parse_measurement_json,
)
from assay.errors import AssayError, InvalidSettings, UnknownMetric

_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def metrics_only_python(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Given a real wheel installed with metrics but without the CLI extra
    root = tmp_path_factory.mktemp("metrics-only-wheel")
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
            f"{wheel}[metrics]",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return environment / "bin" / "python"


def _binary_request() -> BinaryMeasurementRequest:
    return BinaryMeasurementRequest(
        metric="binary",
        metric_version="classification.2026-08",
        y_true=(0, 1, 0, 1),
        y_score=(0.1, 0.9, 0.4, 0.6),
        threshold=0.5,
        controls=BinaryMetricControls(
            min_samples=2,
            bootstrap_resamples=19,
            confidence_level=0.9,
            ece_bins=2,
            bootstrap_seed=7,
        ),
    )


def _ranking_request() -> RankingMeasurementRequest:
    queries = (
        RankingQueryInput(
            query="first",
            judgments=(RelevanceInput(doc_id="a", gain=1),),
            ranked=("a", "x"),
        ),
        RankingQueryInput(
            query="second",
            judgments=(RelevanceInput(doc_id="b", gain=1),),
            ranked=("y", "b"),
        ),
    )
    return RankingMeasurementRequest(
        metric="ranking",
        metric_version="ranking.2026-08",
        queries=queries,
        k=2,
        controls=RankingMetricControls(
            min_samples=2,
            bootstrap_resamples=19,
            confidence_level=0.9,
            bootstrap_seed=7,
        ),
    )


def _agreement_request() -> AgreementMeasurementRequest:
    ratings = (
        OrdinalRating(item="a", rater_a="low", rater_b="low"),
        OrdinalRating(item="b", rater_a="middle", rater_b="high"),
        OrdinalRating(item="c", rater_a="high", rater_b="high"),
    )
    return AgreementMeasurementRequest(
        metric="agreement",
        metric_version="agreement.2026-08",
        scale=("low", "middle", "high"),
        ratings=ratings,
        controls=UncertaintyControls(
            min_samples=2,
            bootstrap_resamples=19,
            confidence_level=0.9,
            bootstrap_seed=7,
        ),
    )


def test_should_return_binary_specific_report_without_universal_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given explicit controls and conflicting environment settings
    monkeypatch.setenv("ASSAY_MIN_SAMPLES", "999")

    # When the typed binary measurement executes
    result = measure(_binary_request())
    payload = result.model_dump(mode="json", by_alias=True)

    # Then all controls are materialized and only binary report families appear
    assert set(payload) == {"schema", "metric", "metric_version", "controls", "report"}
    assert "score" not in payload
    assert "inputs_hash" not in payload
    assert payload["controls"] == {
        "threshold": 0.5,
        "min_samples": 2,
        "bootstrap_resamples": 19,
        "confidence_level": 0.9,
        "ece_bins": 2,
        "bootstrap_seed": 7,
    }
    assert payload["report"]["classification"]["accuracy"] == 1.0
    assert payload["report"]["calibration"]["brier"] == pytest.approx(0.085)
    assert payload["report"]["accuracy_interval"] == {
        "kind": "interval",
        "point": 1.0,
        "low": 1.0,
        "high": 1.0,
    }


def test_should_return_existing_ranking_report_with_explicit_controls() -> None:
    # Given a typed two-query ranking request
    request = _ranking_request()

    # When it is measured
    result = measure(request)
    payload = result.model_dump(mode="json", by_alias=True)

    # Then ranking keeps its native report and interval
    assert payload["metric"] == "ranking"
    assert payload["controls"]["k"] == 2
    assert payload["report"]["n_queries"] == 2
    assert len(payload["report"]["per_query"]) == 2
    assert payload["report"]["ndcg_interval"]["kind"] == "interval"


def test_should_return_existing_agreement_report_with_declared_scale() -> None:
    # Given a typed ordinal request
    request = _agreement_request()

    # When it is measured
    result = measure(request)
    payload = result.model_dump(mode="json", by_alias=True)

    # Then agreement remains a family-specific report
    assert payload["metric"] == "agreement"
    assert payload["controls"]["min_samples"] == 2
    assert payload["report"]["scale"] == ["low", "middle", "high"]
    assert payload["report"]["n_items"] == 3
    assert payload["report"]["weighted_agreement_interval"]["kind"] == "interval"


def test_should_parse_measurement_union_before_optional_execution() -> None:
    # Given a complete binary request serialized as ordinary JSON
    encoded = _binary_request().model_dump_json()

    # When the dependency-light parser validates it
    parsed = parse_measurement_json(encoded)

    # Then the discriminator returns the exact typed family
    assert isinstance(parsed, BinaryMeasurementRequest)
    assert parsed.controls.ece_bins == 2


def test_should_reject_unknown_metric_with_stable_code() -> None:
    # Given a request whose family is not in the closed union
    encoded = json.dumps({"metric": "PRIVATE_FAMILY", "metric_version": "metric.v1"})

    # When / Then the parser refuses it without a dynamic validation message
    with pytest.raises(UnknownMetric, match=r"^assay\.unknown_metric$"):
        parse_measurement_json(encoded)


def test_should_redact_private_values_from_invalid_measurement() -> None:
    # Given a malformed binary request carrying a private sentinel
    encoded = json.dumps(
        {
            "metric": "binary",
            "metric_version": "PRIVATE_SENTINEL",
            "y_true": [0, 1],
            "y_score": [0.1, "PRIVATE_SENTINEL"],
        }
    )

    # When / Then every public error remains code-only
    with pytest.raises(AssayError) as captured:
        parse_measurement_json(encoded)
    assert str(captured.value).startswith("assay.")
    assert "PRIVATE_SENTINEL" not in str(captured.value)


def test_should_identify_invalid_controls_before_metric_family_validation() -> None:
    # Given a known metric whose optional controls violate the bounded settings contract
    payload = _binary_request().model_dump(mode="json")
    payload["controls"]["min_samples"] = 0

    # When / Then settings fail with their own stable value-free code
    with pytest.raises(InvalidSettings, match=r"^assay\.invalid_settings$"):
        parse_measurement_json(json.dumps(payload))


def test_should_freeze_measurement_contracts_and_forbid_extra_fields() -> None:
    # Given a valid immutable binary request
    request = _binary_request()

    # When / Then mutation and ambiguous fields are refused
    with pytest.raises(ValidationError):
        request.threshold = 0.9  # type: ignore[misc]
    with pytest.raises(AssayError):
        BinaryMeasurementRequest(
            **request.model_dump(),
            private_extra="PRIVATE_SENTINEL",
        )


def test_should_execute_library_measurement_from_metrics_only_wheel(
    metrics_only_python: Path, tmp_path: Path
) -> None:
    # Given a clean metrics-only environment and a complete literal request
    program = """
import importlib.util
from assay import measure, parse_measurement_json

assert importlib.util.find_spec("typer") is None
request = parse_measurement_json(
    '{"metric":"binary","metric_version":"classification.v1",'
    '"y_true":[0,1],"y_score":[0.1,0.9],"threshold":0.5,'
    '"controls":{"min_samples":2,"bootstrap_resamples":9,'
    '"confidence_level":0.9,"ece_bins":2,"bootstrap_seed":7}}'
)
result = measure(request)
assert result.metric == "binary"
assert result.report.classification.accuracy == 1.0
"""

    # When measurement is imported and executed outside the repository
    completed = subprocess.run(
        [str(metrics_only_python), "-c", program],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then the library face works without the command dependency
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        (
            {
                "metric": "binary",
                "metric_version": "v" * 257,
                "y_true": [0, 1],
                "y_score": [0.1, 0.9],
            },
            "assay.invalid_contract",
        ),
        (
            {
                "metric": "binary",
                "metric_version": "v1",
                "y_true": [False, 1],
                "y_score": [0.1, 0.9],
            },
            "assay.invalid_request",
        ),
        (
            {
                "metric": "binary",
                "metric_version": "v1",
                "y_true": [0, 1],
                "y_score": [0.1, float("inf")],
            },
            "assay.invalid_request",
        ),
        (
            {"metric": "binary", "metric_version": "v1", "y_true": [0, 1], "y_score": [0.1, 1.1]},
            "assay.invalid_request",
        ),
        (
            {"metric": "binary", "metric_version": "v1", "y_true": [0], "y_score": [0.1, 0.9]},
            "assay.invalid_request",
        ),
        (
            {"metric": "binary", "metric_version": "v1", "y_true": [0, 0], "y_score": [0.1, 0.2]},
            "assay.invalid_request",
        ),
        (
            {
                "metric": "ranking",
                "metric_version": "v1",
                "queries": [
                    {"query": "q", "judgments": [{"doc_id": "a", "gain": 0.5}], "ranked": ["a"]}
                ],
            },
            "assay.invalid_ranking_request",
        ),
        (
            {
                "metric": "ranking",
                "metric_version": "v1",
                "queries": [
                    {
                        "query": "q",
                        "judgments": [{"doc_id": "a", "gain": 1}, {"doc_id": "a", "gain": 1}],
                        "ranked": ["a"],
                    }
                ],
            },
            "assay.invalid_ranking_request",
        ),
        (
            {
                "metric": "ranking",
                "metric_version": "v1",
                "queries": [
                    {"query": "q", "judgments": [{"doc_id": "a", "gain": 1}], "ranked": ["a", "a"]}
                ],
            },
            "assay.invalid_ranking_request",
        ),
        (
            {
                "metric": "ranking",
                "metric_version": "v1",
                "queries": [
                    {"query": "q", "judgments": [{"doc_id": "a", "gain": 0}], "ranked": ["a"]}
                ],
            },
            "assay.empty_relevant_set",
        ),
        (
            {
                "metric": "agreement",
                "metric_version": "v1",
                "scale": ["low", "low"],
                "ratings": [{"item": "a", "rater_a": "low", "rater_b": "low"}],
            },
            "assay.invalid_agreement_request",
        ),
        (
            {
                "metric": "agreement",
                "metric_version": "v1",
                "scale": ["low", "high"],
                "ratings": [{"item": "a", "rater_a": "low", "rater_b": "missing"}],
            },
            "assay.invalid_agreement_request",
        ),
    ],
)
def test_should_reject_each_malformed_family_before_dependency_execution(
    payload: dict[str, object], error_code: str
) -> None:
    # Given one malformed request in the closed measurement union
    # When / Then parsing fails with the family-specific value-free code
    with pytest.raises(AssayError, match=rf"^{re.escape(error_code)}$"):
        parse_measurement_json(json.dumps(payload))


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("[]", id="array"),
        pytest.param("{", id="truncated"),
        pytest.param(b"\xff", id="non-utf8"),
        pytest.param(
            "[" * 10_000 + "0" + "]" * 10_000,
            id="deeply-nested",
        ),
    ],
)
def test_should_reject_nonobject_or_malformed_measurement_json(
    payload: str | bytes,
) -> None:
    # Given bytes that cannot represent a measurement object
    # When / Then the JSON boundary returns one stable contract code
    with pytest.raises(AssayError, match=r"^assay\.invalid_contract$"):
        parse_measurement_json(payload)
