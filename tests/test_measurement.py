"""Typed three-family measurement contract and execution."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from assay import (
    AgreementMeasurementRequest,
    AgreementMeasurementResult,
    BinaryMeasurementRequest,
    BinaryMeasurementResult,
    BinaryMetricControls,
    OrdinalRating,
    RankingMeasurementRequest,
    RankingMeasurementResult,
    RankingMetricControls,
    RankingQueryInput,
    RelevanceInput,
    UncertaintyControls,
    measure,
    parse_measurement_json,
)
from assay.errors import AssayError, InvalidSettings, UnknownMetric
from assay.measurement import BinaryMeasurementReport

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


def test_should_reject_forged_binary_result_on_every_validation_path() -> None:
    # Given NaN, coercive text, negative counts, oversized controls, and inverted bounds
    result = measure(_binary_request())
    coercive = result.model_dump(mode="json", by_alias=True)
    coercive_report = coercive["report"]
    assert isinstance(coercive_report, dict)
    classification = coercive_report["classification"]
    assert isinstance(classification, dict)
    classification["accuracy"] = "0.5"

    # When / Then direct construction rejects numeric coercion
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult(
            metric="binary",
            metric_version=result.metric_version,
            controls=result.controls,
            report=coercive_report,
        )

    # Given a distinct report with a negative confusion cell
    negative = result.model_dump(mode="json", by_alias=True)
    negative_report = negative["report"]
    assert isinstance(negative_report, dict)
    negative_classification = negative_report["classification"]
    assert isinstance(negative_classification, dict)
    counts = negative_classification["counts"]
    assert isinstance(counts, dict)
    counts["false_negatives"] = -1

    # When / Then direct validation rejects the negative family value independently
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate(negative)

    # Given a valid wire whose uncertainty bounds contradict their point
    wire = result.model_dump(mode="json", by_alias=True)
    wire_report = wire["report"]
    assert isinstance(wire_report, dict)
    interval = wire_report["accuracy_interval"]
    assert isinstance(interval, dict)
    interval.update({"low": 1.1, "high": 0.9})

    # When / Then JSON validation rejects the inverted bounds without details
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(wire))

    # When / Then copy validation rejects an oversized result control
    controls = {**result.controls.model_dump(), "bootstrap_resamples": 1_000_001}
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        result.model_copy(update={"controls": controls})

    # When / Then a model_construct forgery is revalidated rather than trusted
    forged_scores = replace(result.report.classification, accuracy=float("nan"))
    forged_report = BinaryMeasurementReport.model_construct(
        classification=forged_scores,
        calibration=result.report.calibration,
        accuracy_interval=result.report.accuracy_interval,
    )
    forged = BinaryMeasurementResult.model_construct(
        schema_version="assay.measurement/v1",
        metric="binary",
        metric_version=result.metric_version,
        controls=result.controls,
        report=forged_report,
    )
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate(forged)


def test_should_reject_binary_precision_that_disagrees_with_counts() -> None:
    # Given a binary report claiming imperfect precision with zero false positives
    result = measure(_binary_request())
    report = result.report.model_dump(mode="python")
    classification = report["classification"]
    assert isinstance(classification, dict)
    classification["precision"] = 0.125

    # When / Then direct result construction refuses the contradictory summary
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult(
            metric="binary",
            metric_version=result.metric_version,
            controls=result.controls,
            report=report,
        )


def test_should_accept_generated_binary_summary_with_one_ulp_f1_rounding() -> None:
    # Given counts whose sklearn F1 differs by one ULP from replayed precision/recall
    request = BinaryMeasurementRequest(
        metric="binary",
        metric_version="classification.2026-08",
        y_true=(1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0),
        y_score=(0.9, 0.8, 0.7, 0.4, 0.3, 0.2, 0.9, 0.8, 0.7, 0.6, 0.2, 0.1),
        controls=BinaryMetricControls(
            min_samples=13,
            bootstrap_resamples=19,
            confidence_level=0.9,
            ece_bins=4,
            bootstrap_seed=7,
        ),
    )

    # When the genuine native report is wrapped and replayed
    result = measure(request)

    # Then binary64 engine rounding remains accepted as the same derived summary
    assert result.report.classification.counts.false_positives == 4
    assert type(result).model_validate_json(result.model_dump_json(by_alias=True)) == result


def test_should_reject_binary_ece_that_disagrees_with_reliability_bins() -> None:
    # Given a wire whose bins still imply ECE 0.25 but whose summary claims 0.5
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    calibration = report["calibration"]
    assert isinstance(calibration, dict)
    calibration["ece"] = 0.5

    # When / Then JSON replay refuses the inconsistent calibration summary
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_binary_calibration_population_that_disagrees_with_counts() -> None:
    # Given internally consistent ECE bins that erase every observed positive
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    calibration = report["calibration"]
    assert isinstance(calibration, dict)
    bins = calibration["bins"]
    assert isinstance(bins, list)
    assert isinstance(bins[1], dict)
    bins[1]["fraction_positive"] = 0.0
    calibration["ece"] = 0.5

    # When / Then Python replay refuses the population contradiction
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate(payload)


def test_should_reject_result_claiming_over_budget_bootstrap_work() -> None:
    # Given a valid 30-item result edited to claim one million resamples
    request = _binary_request().model_copy(
        update={
            "y_true": tuple(index % 2 for index in range(30)),
            "y_score": tuple(0.75 if index % 2 else 0.25 for index in range(30)),
            "controls": {**_binary_request().controls.model_dump(), "min_samples": 30},
        }
    )
    result = measure(request)
    controls = {**result.controls.model_dump(), "bootstrap_resamples": 1_000_000}

    # When / Then validated copy rejects the claimed 30-million-cell workload
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        result.model_copy(update={"controls": controls})


def test_should_revalidate_constructed_binary_summary_before_serializing() -> None:
    # Given a model_construct result whose precision contradicts its native counts
    result = measure(_binary_request())
    scores = replace(result.report.classification, precision=0.125)
    report = BinaryMeasurementReport.model_construct(
        classification=scores,
        calibration=result.report.calibration,
        accuracy_interval=result.report.accuracy_interval,
    )
    forged = BinaryMeasurementResult.model_construct(
        schema_version="assay.measurement/v1",
        metric="binary",
        metric_version=result.metric_version,
        controls=result.controls,
        report=report,
    )

    # When / Then the serialization boundary refuses the forged summary
    with pytest.raises(PydanticSerializationError, match=r"assay\.invalid_request") as caught:
        forged.model_dump_json(by_alias=True)
    assert "0.125" not in str(caught.value)


def test_should_reject_forged_ranking_result_invariants() -> None:
    # Given a ranking result whose counts, controls, and interval disagree
    result = measure(_ranking_request())
    payload = result.model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    report["n_queries"] = -1
    report["k"] = "2"

    # When / Then family validation is strict and value-free
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        RankingMeasurementResult.model_validate_json(json.dumps(payload))

    # Given a valid report whose query count no longer matches its rows
    mismatch = result.model_dump(mode="json", by_alias=True)
    mismatch_report = mismatch["report"]
    assert isinstance(mismatch_report, dict)
    mismatch_report["n_queries"] = 3

    # When / Then standalone result replay refuses the contradiction
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        RankingMeasurementResult.model_validate(mismatch)


@pytest.mark.parametrize(
    "field",
    [
        "mean_precision_at_k",
        "mean_recall_at_k",
        "mean_f1_at_k",
        "mrr",
        "mean_average_precision",
    ],
)
def test_should_reject_ranking_aggregate_that_disagrees_with_query_rows(field: str) -> None:
    # Given a ranking report whose aggregate no longer summarizes its query rows
    payload = measure(_ranking_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    report[field] = 0.123

    # When / Then replay refuses every contradictory aggregate with one family code
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        RankingMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_forged_agreement_result_invariants() -> None:
    # Given an agreement result with coercive counts and inverted uncertainty
    result = measure(_agreement_request())
    payload = result.model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    report["n_items"] = "3"
    interval = report["weighted_agreement_interval"]
    assert isinstance(interval, dict)
    interval.update({"low": 0.9, "high": 0.1})

    # When / Then JSON replay returns only the agreement-family error
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        AgreementMeasurementResult.model_validate_json(json.dumps(payload))

    # Given a count that contradicts the exact-match population
    mismatch = result.model_dump(mode="json", by_alias=True)
    mismatch_report = mismatch["report"]
    assert isinstance(mismatch_report, dict)
    mismatch_report["n_exact_matches"] = 4

    # When / Then direct replay refuses it
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        AgreementMeasurementResult.model_validate(mismatch)


def test_should_redact_finite_integer_overflow_in_measurement_json() -> None:
    # Given a valid sub-limit JSON number whose binary64 conversion overflows
    huge = "9" * 1_000
    request = (
        '{"metric":"binary","metric_version":"classification.2026-08",'
        f'"y_true":[0,1],"y_score":[0.1,{huge}]}}'
    )

    # When / Then request parsing returns only the binary family code
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$") as caught:
        parse_measurement_json(request)
    assert huge not in repr(caught.value)

    # Given the same value forged into a binary result wire
    result = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = result["report"]
    assert isinstance(report, dict)
    classification = report["classification"]
    assert isinstance(classification, dict)
    classification["accuracy"] = int(huge)

    # When / Then result replay returns the same stable family code
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(result))


def test_should_reject_duplicate_measurement_request_json_members() -> None:
    # Given a valid binary request with a conflicting repeated discriminator
    payload = json.dumps(_binary_request().model_dump(mode="json"), separators=(",", ":"))
    duplicate = payload.replace(
        '"metric":"binary"', '"metric":"PRIVATE_FIRST","metric":"binary"', 1
    )

    # When / Then union and direct-model parsers reject it before last-wins validation
    for parse in (parse_measurement_json, BinaryMeasurementRequest.model_validate_json):
        with pytest.raises(AssayError, match=r"^assay\.duplicate_field$") as caught:
            parse(duplicate)
        assert "PRIVATE" not in repr(caught.value)


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(lambda: measure(_binary_request()), id="binary"),
        pytest.param(lambda: measure(_ranking_request()), id="ranking"),
        pytest.param(lambda: measure(_agreement_request()), id="agreement"),
    ],
)
def test_should_reject_duplicate_measurement_result_json_members(result: object) -> None:
    # Given a valid family result with a repeated metric member
    measured = result()
    payload = measured.model_dump_json(by_alias=True)
    duplicate = payload.replace('"metric":', '"metric":"PRIVATE_FIRST","metric":', 1)

    # When / Then its public result replay rejects the duplicate before family validation
    with pytest.raises(AssayError, match=r"^assay\.duplicate_field$") as caught:
        type(measured).model_validate_json(duplicate)
    assert "PRIVATE" not in repr(caught.value)


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
