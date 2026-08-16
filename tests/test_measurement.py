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


def _abstaining_agreement_result() -> AgreementMeasurementResult:
    controls = _agreement_request().controls.model_copy(update={"min_samples": 4})
    request = _agreement_request().model_copy(update={"controls": controls})
    return measure(request)


def _contradictory_agreement() -> tuple[AgreementMeasurementResult, dict[str, object]]:
    result = _abstaining_agreement_result()
    payload = result.model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    report["weighted_agreement"] = 0.1
    return result, payload


def _constructed_agreement(result: AgreementMeasurementResult) -> AgreementMeasurementResult:
    forged = result.report.model_copy(update={"weighted_agreement": 0.1})
    data = result.model_dump(exclude={"report"})
    return AgreementMeasurementResult.model_construct(**data, report=forged)


def _two_level_agreement_result() -> AgreementMeasurementResult:
    ratings = (
        OrdinalRating(item="exact", rater_a="low", rater_b="low"),
        OrdinalRating(item="miss", rater_a="high", rater_b="low"),
    )
    controls = _agreement_request().controls.model_copy(update={"min_samples": 3})
    request = _agreement_request().model_copy(
        update={"scale": ("low", "high"), "ratings": ratings, "controls": controls}
    )
    return measure(request)


def _varying_exact_agreement_result() -> AgreementMeasurementResult:
    ratings = tuple(
        OrdinalRating(item=band, rater_a=band, rater_b=band) for band in ("low", "middle", "high")
    )
    return measure(_agreement_request().model_copy(update={"ratings": ratings}))


def _agreement_payload(
    result: AgreementMeasurementResult, changes: dict[str, object]
) -> dict[str, object]:
    payload = result.model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    report.update(changes)
    return payload


def _replay_agreement(
    boundary: str, result: AgreementMeasurementResult, changes: dict[str, object]
) -> object:
    payload = _agreement_payload(result, changes)
    if boundary == "constructor":
        data = result.model_dump(exclude={"report"})
        return AgreementMeasurementResult(**data, report=payload["report"])
    if boundary == "json":
        return AgreementMeasurementResult.model_validate_json(json.dumps(payload))
    if boundary == "copy":
        return result.model_copy(update={"report": payload["report"]})
    report = result.report.model_copy(update=changes)
    data = result.model_dump(exclude={"report"})
    forged = AgreementMeasurementResult.model_construct(**data, report=report)
    return forged.model_dump_json(by_alias=True)


def _single_ranking_result(
    query: RankingQueryInput | None = None, *, k: int = 2, min_samples: int = 2
) -> RankingMeasurementResult:
    request = _ranking_request()
    selected = request.queries[0] if query is None else query
    controls = request.controls.model_copy(update={"min_samples": min_samples})
    return measure(
        request.model_copy(update={"queries": (selected,), "k": k, "controls": controls})
    )


def _ranking_changes(
    result: RankingMeasurementResult, row_changes: dict[str, object]
) -> dict[str, object]:
    row = result.report.per_query[0].model_copy(update=row_changes)
    return {
        "per_query": (row,),
        "mean_precision_at_k": row.precision_at_k,
        "mean_recall_at_k": row.recall_at_k,
        "mean_f1_at_k": row.f1_at_k,
        "mean_ndcg_at_k": row.ndcg_at_k,
        "mrr": row.reciprocal_rank,
        "mean_average_precision": row.average_precision,
    }


def _replay_ranking(
    boundary: str, result: RankingMeasurementResult, changes: dict[str, object]
) -> object:
    report = result.report.model_copy(update=changes)
    data = result.model_dump(exclude={"report"})
    if boundary == "constructor":
        return RankingMeasurementResult(**data, report=report)
    if boundary == "json":
        payload = result.model_dump(mode="json", by_alias=True)
        payload["report"] = report.model_dump(mode="json")
        return RankingMeasurementResult.model_validate_json(json.dumps(payload))
    if boundary == "copy":
        return result.model_copy(update={"report": report})
    forged = RankingMeasurementResult.model_construct(**data, report=report)
    return forged.model_dump_json(by_alias=True)


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


def test_should_reject_binary_result_without_both_observed_classes() -> None:
    # Given a result whose counts and bins consistently claim four positives and no negatives
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    classification = report["classification"]
    calibration = report["calibration"]
    assert isinstance(classification, dict)
    assert isinstance(calibration, dict)
    classification["counts"] = {
        "true_positives": 4,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0,
    }
    bins = calibration["bins"]
    assert isinstance(bins, list)
    for row in bins:
        assert isinstance(row, dict)
        row["fraction_positive"] = 1.0
    calibration.update({"ece": 0.5, "brier": 0.335})

    # When / Then replay refuses a population on which the reported AUCs cannot exist
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate(payload)


def test_should_reject_fractional_positive_count_inside_calibration_bin() -> None:
    # Given two size-two bins each claiming half of a positive observation
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    calibration = report["calibration"]
    assert isinstance(calibration, dict)
    bins = calibration["bins"]
    assert isinstance(bins, list)
    assert all(isinstance(row, dict) for row in bins)
    bins[0]["fraction_positive"] = 0.25
    bins[1]["fraction_positive"] = 0.75
    calibration["ece"] = 0.0

    # When / Then replay rejects bin fractions that imply non-integer populations
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_calibration_error_larger_than_brier_root() -> None:
    # Given native reliability bins and ECE but a Brier score too small to support that gap
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    calibration = report["calibration"]
    assert isinstance(calibration, dict)
    calibration["brier"] = 0.01

    # When / Then replay enforces the necessary ECE-squared lower bound on Brier loss
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_brier_below_per_bin_feasibility_floor() -> None:
    # Given two bins with one positive each and a loss below their best possible scores
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    calibration = report["calibration"]
    assert isinstance(calibration, dict)
    bins = calibration["bins"]
    assert isinstance(bins, list)
    for row in bins:
        assert isinstance(row, dict)
        row["fraction_positive"] = 0.5
    calibration.update({"ece": 0.25, "brier": 0.08})

    # When / Then replay rejects loss below the bin-derived minimum of 0.125
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_reliability_bins_out_of_score_order() -> None:
    # Given two populated calibration bins presented in descending prediction order
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    calibration = report["calibration"]
    assert isinstance(calibration, dict)
    bins = calibration["bins"]
    assert isinstance(bins, list)
    assert isinstance(bins[0], dict)
    assert isinstance(bins[1], dict)
    bins[0]["mean_predicted"] = 0.75
    bins[1]["mean_predicted"] = 0.25
    calibration.update({"ece": 0.75, "brier": 0.625})

    # When / Then replay preserves calibration_curve's increasing bin order
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_zero_average_precision_with_observed_positives() -> None:
    # Given both observed classes but a claimed zero average precision
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    classification = report["classification"]
    assert isinstance(classification, dict)
    classification["pr_auc"] = 0.0

    # When / Then replay rejects an AP value impossible when positives exist
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_roc_auc_outside_threshold_count_bounds() -> None:
    # Given perfect threshold counts but a claimed chance-level ROC AUC
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    classification = report["classification"]
    assert isinstance(classification, dict)
    classification["roc_auc"] = 0.5

    # When / Then replay uses the known threshold ordering to require ROC AUC one
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_roc_auc_outside_the_finite_pair_grid() -> None:
    # Given mixed threshold counts but an AUC not representable by four positive-negative pairs
    controls = _binary_request().controls.model_copy(update={"min_samples": 5})
    request = _binary_request().model_copy(
        update={"y_score": (0.9, 0.8, 0.7, 0.6), "threshold": 0.75, "controls": controls}
    )
    payload = measure(request).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    classification = report["classification"]
    assert isinstance(classification, dict)
    classification["roc_auc"] = 0.3

    # When / Then replay requires integer or half-credit ordering over the four pairs
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_noncollapsed_accuracy_interval_for_constant_correctness() -> None:
    # Given a perfect native classifier whose per-sample correctness is constant one
    payload = measure(_binary_request()).model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    interval = report["accuracy_interval"]
    assert isinstance(interval, dict)
    interval["low"] = 0.9

    # When / Then replay requires its percentile interval to collapse at one
    with pytest.raises(AssayError, match=r"^assay\.invalid_request$"):
        BinaryMeasurementResult.model_validate_json(json.dumps(payload))


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


@pytest.mark.parametrize("boundary", ["constructor", "json", "copy", "serialize"])
def test_should_reject_fractional_precision_hit_count(boundary: str) -> None:
    # Given a one-query result claiming 0.6 precision at k=2, or 1.2 relevant hits
    result = _single_ranking_result()
    changes = _ranking_changes(result, {"precision_at_k": 0.6, "f1_at_k": 0.75})
    error = PydanticSerializationError if boundary == "serialize" else AssayError

    # When / Then every replay boundary rejects the non-integer hit numerator
    with pytest.raises(error, match=r"assay\.invalid_ranking_request"):
        _replay_ranking(boundary, result, changes)


@pytest.mark.parametrize("boundary", ["constructor", "json", "copy", "serialize"])
def test_should_reject_zero_precision_with_nonzero_recall(boundary: str) -> None:
    # Given a row claiming no top-k hits but nonzero recall from those same hits
    result = _single_ranking_result()
    changes = _ranking_changes(
        result,
        {"precision_at_k": 0.0, "recall_at_k": 1.0, "f1_at_k": 0.0, "ndcg_at_k": 0.0},
    )
    error = PydanticSerializationError if boundary == "serialize" else AssayError

    # When / Then every replay boundary rejects the contradictory shared numerator
    with pytest.raises(error, match=r"assay\.invalid_ranking_request"):
        _replay_ranking(boundary, result, changes)


def test_should_accept_native_trec_eval_fraction_and_late_hit_boundaries() -> None:
    # Given one query with 2/3 precision and another whose only hit falls after k
    cut = RankingQueryInput(
        query="cut",
        judgments=tuple(RelevanceInput(doc_id=doc, gain=1) for doc in ("a", "b", "c", "d")),
        ranked=("a", "x", "b"),
    )
    late = RankingQueryInput(
        query="late",
        judgments=(RelevanceInput(doc_id="a", gain=1),),
        ranked=("x", "y", "a"),
    )
    results = (_single_ranking_result(cut, k=3), _single_ranking_result(late))

    # When / Then exact trec_eval rows replay without inventing raw-input proof
    assert results[0].report.per_query[0].precision_at_k == pytest.approx(2 / 3)
    assert results[0].report.per_query[0].recall_at_k == pytest.approx(1 / 2)
    assert results[1].report.per_query[0].reciprocal_rank == pytest.approx(1 / 3)
    assert all(
        type(result).model_validate_json(result.model_dump_json()) == result for result in results
    )


def test_should_reject_recall_without_an_integer_relevant_population() -> None:
    # Given one hit at k=2 but recall 0.4, which would require 2.5 relevant documents
    result = _single_ranking_result()
    changes = _ranking_changes(result, {"recall_at_k": 0.4, "f1_at_k": 0.4444444444444445})

    # When / Then replay rejects the impossible relevance-count denominator
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        _replay_ranking("json", result, changes)


def test_should_reject_nonreciprocal_reciprocal_rank() -> None:
    # Given a reciprocal-rank value of 0.4, which is not 1 divided by an integer position
    result = _single_ranking_result()
    changes = _ranking_changes(result, {"reciprocal_rank": 0.4})

    # When / Then replay rejects a value no ranked position could produce
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        _replay_ranking("json", result, changes)


def test_should_reject_first_hit_position_incompatible_with_top_k_hit_count() -> None:
    # Given one top-two hit but a reciprocal rank claiming the first hit was at position three
    result = _single_ranking_result()
    changes = _ranking_changes(result, {"reciprocal_rank": 1 / 3})

    # When / Then replay requires that hit to occur within the top-two window
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        _replay_ranking("json", result, changes)


def test_should_reject_average_precision_zero_state_that_disagrees_with_rank() -> None:
    # Given a row with a first relevant hit but a claimed zero average precision
    result = _single_ranking_result()
    changes = _ranking_changes(result, {"average_precision": 0.0})

    # When / Then replay requires AP and reciprocal rank to agree on whether any hit exists
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        _replay_ranking("json", result, changes)


def test_should_reject_ndcg_zero_state_that_disagrees_with_top_k_hits() -> None:
    # Given a row claiming a top-k hit through precision but zero top-k gain through nDCG
    result = _single_ranking_result()
    changes = _ranking_changes(result, {"ndcg_at_k": 0.0})

    # When / Then replay requires both top-k metrics to agree on whether a hit exists
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        _replay_ranking("json", result, changes)


def test_should_measure_and_replay_duplicate_query_text() -> None:
    # Given two distinct ranking rows that use the same human-readable query text
    request = _ranking_request()
    first, second = request.queries
    duplicated = request.model_copy(
        update={
            "queries": (
                first.model_copy(update={"query": "same question"}),
                second.model_copy(update={"query": "same question"}),
            )
        }
    )

    # When the valid request is measured and its result JSON is replayed
    result = measure(duplicated)
    replayed = RankingMeasurementResult.model_validate_json(result.model_dump_json())

    # Then query text stays non-unique while both rows and their means remain intact
    assert result.report.n_queries == 2
    assert tuple(row.query for row in result.report.per_query) == ("same question", "same question")
    assert replayed == result


def test_should_reject_noncollapsed_ndcg_interval_for_one_query() -> None:
    # Given a one-query native result whose every resample has the same nDCG
    result = _single_ranking_result(min_samples=1)
    interval = result.report.ndcg_interval
    assert interval.kind == "interval"
    forged_interval = replace(interval, low=0.5)
    report = result.report.model_copy(update={"ndcg_interval": forged_interval})

    # When / Then replay requires the constant bootstrap interval to collapse
    with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$"):
        result.model_copy(update={"report": report})


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


def test_should_reject_weighted_agreement_below_exact_rate_in_constructor() -> None:
    # Given an abstaining report claiming exact matches contribute less than one
    result, payload = _contradictory_agreement()

    # When / Then direct construction rejects the impossible weighted aggregate
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        AgreementMeasurementResult(
            metric="agreement",
            metric_version=result.metric_version,
            controls=result.controls,
            report=payload["report"],
        )


def test_should_reject_weighted_agreement_below_exact_rate_in_json() -> None:
    # Given an abstaining agreement wire with weighted agreement below 2/3
    _, payload = _contradictory_agreement()

    # When / Then JSON replay returns only the stable agreement-family code
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        AgreementMeasurementResult.model_validate_json(json.dumps(payload))


def test_should_reject_weighted_agreement_below_exact_rate_in_copy() -> None:
    # Given a valid result and a contradictory report update
    result, payload = _contradictory_agreement()

    # When / Then validated copying cannot install the contradiction
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        result.model_copy(update={"report": payload["report"]})


def test_should_reject_constructed_weighted_contradiction_when_serializing() -> None:
    # Given model_construct bypassed validation for an impossible agreement report
    result, _ = _contradictory_agreement()
    forged = _constructed_agreement(result)

    # When / Then serialization revalidates and emits no forged number
    with pytest.raises(
        PydanticSerializationError, match=r"assay\.invalid_agreement_request"
    ) as caught:
        forged.model_dump_json(by_alias=True)
    assert "0.1" not in str(caught.value)


@pytest.mark.parametrize("field", ["quadratic_kappa", "kendall_tau_b"])
def test_should_reject_nonperfect_statistic_from_all_exact_ratings(field: str) -> None:
    # Given all ratings match but one correlation statistic claims 0.5
    result = _constant_agreement_result()
    payload = result.model_dump(mode="json", by_alias=True)
    report = payload["report"]
    assert isinstance(report, dict)
    report[field] = 0.5
    report[f"{'kappa' if field == 'quadratic_kappa' else 'tau'}_undefined_reason"] = None

    # When / Then replay refuses a defined all-exact statistic below one
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        AgreementMeasurementResult.model_validate_json(json.dumps(payload))


def _constant_agreement_result() -> AgreementMeasurementResult:
    ratings = tuple(
        OrdinalRating(item=str(index), rater_a="low", rater_b="low") for index in range(3)
    )
    request = _agreement_request().model_copy(update={"ratings": ratings})
    return measure(request)


@pytest.mark.parametrize("boundary", ["constructor", "json", "copy", "serialize"])
def test_should_reject_weighted_gain_from_mismatch_on_two_level_scale(boundary: str) -> None:
    # Given a binary scale where one exact row and one mismatch can only average to 0.5
    result = _two_level_agreement_result()
    error = PydanticSerializationError if boundary == "serialize" else AssayError

    # When / Then every replay boundary rejects a claimed weighted agreement of 0.9
    with pytest.raises(error, match=r"assay\.invalid_agreement_request"):
        _replay_agreement(boundary, result, {"weighted_agreement": 0.9})


@pytest.mark.parametrize("boundary", ["constructor", "json", "copy", "serialize"])
def test_should_reject_weight_above_the_scale_mismatch_bound(boundary: str) -> None:
    # Given two exact rows and one adjacent miss on a three-level scale
    result = _abstaining_agreement_result()
    error = PydanticSerializationError if boundary == "serialize" else AssayError

    # When / Then 0.99 is rejected because the greatest possible mean is 11/12
    with pytest.raises(error, match=r"assay\.invalid_agreement_request"):
        _replay_agreement(boundary, result, {"weighted_agreement": 0.99})


@pytest.mark.parametrize("boundary", ["constructor", "json", "copy", "serialize"])
def test_should_reject_undefined_kappa_from_partial_agreement(boundary: str) -> None:
    # Given a non-all-exact result claiming quadratic kappa cannot be defined
    result = _abstaining_agreement_result()
    changes = {"quadratic_kappa": None, "kappa_undefined_reason": "statistic undefined"}
    error = PydanticSerializationError if boundary == "serialize" else AssayError

    # When / Then every replay boundary requires the partial result's defined kappa
    with pytest.raises(error, match=r"assay\.invalid_agreement_request"):
        _replay_agreement(boundary, result, changes)


def test_should_accept_maximum_adjacent_weight_and_constant_rater_tau_abstention() -> None:
    # Given a native adjacent mismatch at the upper bound and partial constant-rater data
    maximum = _abstaining_agreement_result()
    ratings = (
        OrdinalRating(item="a", rater_a="low", rater_b="low"),
        OrdinalRating(item="b", rater_a="low", rater_b="middle"),
        OrdinalRating(item="c", rater_a="low", rater_b="high"),
    )
    constant = measure(_agreement_request().model_copy(update={"ratings": ratings}))

    # When / Then native rounding passes and tau alone may remain undefined
    assert maximum.report.weighted_agreement == pytest.approx(11 / 12)
    assert constant.report.quadratic_kappa == 0.0
    assert constant.report.kendall_tau_b is None
    assert all(
        type(result).model_validate_json(result.model_dump_json()) == result
        for result in (maximum, constant)
    )


def test_should_reject_quadratic_kappa_above_observed_weighted_agreement() -> None:
    # Given partial agreement claiming chance correction improved the observed agreement
    result = _abstaining_agreement_result()

    # When / Then replay rejects kappa above its weighted observed agreement
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        _replay_agreement("json", result, {"quadratic_kappa": 0.99})


def test_should_reject_weight_not_reachable_from_ordinal_distance_squares() -> None:
    # Given a three-item, three-level report whose 0.9 weight implies distance cost 1.2
    result = _abstaining_agreement_result()

    # When / Then replay rejects a mean outside the discrete quadratic-weight lattice
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        _replay_agreement("json", result, {"weighted_agreement": 0.9})


@pytest.mark.parametrize("boundary", ["constructor", "json", "copy", "serialize"])
@pytest.mark.parametrize("mode", ["constant", "varying"])
def test_should_reject_mixed_defined_state_from_all_exact_statistics(
    boundary: str, mode: str
) -> None:
    # Given an all-exact result mixing one defined statistic with one undefined statistic
    result = (
        _constant_agreement_result() if mode == "constant" else _varying_exact_agreement_result()
    )
    changes = (
        {"quadratic_kappa": 1.0, "kappa_undefined_reason": None}
        if mode == "constant"
        else {"kendall_tau_b": None, "tau_undefined_reason": "statistic undefined"}
    )
    error = PydanticSerializationError if boundary == "serialize" else AssayError

    # When / Then every replay boundary refuses the impossible mixed state
    with pytest.raises(error, match=r"assay\.invalid_agreement_request"):
        _replay_agreement(boundary, result, changes)


def test_should_accept_degenerate_and_varying_all_exact_agreement_results() -> None:
    # Given valid all-exact results with constant and varying ratings
    constant = _constant_agreement_result()
    varying = _varying_exact_agreement_result()

    # When / Then undefined degeneracy and defined perfect correlation both replay
    assert constant.report.quadratic_kappa is None
    assert constant.report.kendall_tau_b is None
    assert constant.report.kappa_undefined_reason is not None
    assert constant.report.tau_undefined_reason is not None
    assert varying.report.quadratic_kappa == 1.0
    assert varying.report.kendall_tau_b == 1.0
    assert varying.report.kappa_undefined_reason is None
    assert varying.report.tau_undefined_reason is None
    assert all(
        type(result).model_validate_json(result.model_dump_json(by_alias=True)) == result
        for result in (constant, varying)
    )


def test_should_reject_noncollapsed_agreement_interval_for_all_exact_items() -> None:
    # Given an all-exact result whose per-item weights are constant one
    result = _constant_agreement_result()
    interval = result.report.weighted_agreement_interval
    assert interval.kind == "interval"
    forged = {"kind": "interval", "point": 1.0, "low": 0.9, "high": 1.0}

    # When / Then replay requires its percentile interval to collapse at one
    with pytest.raises(AssayError, match=r"^assay\.invalid_agreement_request$"):
        _replay_agreement("json", result, {"weighted_agreement_interval": forged})


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


def test_should_map_oversized_ranking_gain_to_context_free_family_error() -> None:
    # Given a valid ranking request whose gain is a 1,000-digit integer
    huge = 10**999
    payload = _ranking_request().model_dump(mode="json")
    queries = payload["queries"]
    assert isinstance(queries, list)
    assert isinstance(queries[0], dict)
    judgments = queries[0]["judgments"]
    assert isinstance(judgments, list)
    assert isinstance(judgments[0], dict)
    judgments[0]["gain"] = huge

    # When / Then constructor and JSON parsing use only the ranking family error
    for operation in (
        lambda: RelevanceInput(doc_id="a", gain=huge),
        lambda: parse_measurement_json(json.dumps(payload)),
    ):
        with pytest.raises(AssayError, match=r"^assay\.invalid_ranking_request$") as caught:
            operation()
        assert caught.value.__context__ is None
        assert caught.value.__cause__ is None
        assert str(huge) not in repr(caught.value)


@pytest.mark.parametrize(
    "model",
    [_binary_request(), _ranking_request(), _agreement_request()],
    ids=["binary", "ranking", "agreement"],
)
def test_should_map_oversized_confidence_to_context_free_settings_error(model: object) -> None:
    # Given each family request with a 1,000-digit confidence level
    assert isinstance(
        model,
        (BinaryMeasurementRequest, RankingMeasurementRequest, AgreementMeasurementRequest),
    )
    payload = model.model_dump(mode="json")
    controls = payload["controls"]
    assert isinstance(controls, dict)
    controls["confidence_level"] = 10**999

    # When / Then shared controls expose only the settings-family error without context
    with pytest.raises(InvalidSettings, match=r"^assay\.invalid_settings$") as caught:
        parse_measurement_json(json.dumps(payload))
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


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
