"""Strict three-family measurement contracts and optional metric dispatch."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Annotated, ClassVar, Final, Literal, Self, cast, overload

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)
from pydantic.config import ExtraValues

from assay._json import decode_json
from assay.agreement import AgreementReport, agreement_report
from assay.calibration import CalibrationReport, calibration_report
from assay.errors import (
    AssayError,
    ContractValidationError,
    EmptyRelevantSet,
    InvalidAgreementRequest,
    InvalidRankingRequest,
    InvalidScoreRequest,
    InvalidSettings,
    UnknownMetric,
)
from assay.limits import (
    MAX_BOOTSTRAP_RESAMPLES,
    MAX_BOOTSTRAP_WORK_CELLS,
    MAX_CALIBRATION_BINS,
    MAX_ITEMS,
    MAX_RANKING_K,
    MAX_RELEVANCE_GAIN,
    MAX_SCALE_LEVELS,
    MAX_SEED,
)
from assay.metrics import ClassificationScores, binary_scores, correctness, require_metrics_extra
from assay.models import ItemRating, RankedQuery, RelevanceJudgment
from assay.ranking import RankingReport, ranking_report
from assay.settings import AssaySettings
from assay.uncertainty import Abstention, Estimate, Interval, mean_interval

__all__ = [
    "AgreementMeasurementRequest",
    "AgreementMeasurementResult",
    "BinaryMeasurementRequest",
    "BinaryMeasurementResult",
    "BinaryMetricControls",
    "MeasurementRequest",
    "MeasurementResult",
    "OrdinalRating",
    "RankingMeasurementRequest",
    "RankingMeasurementResult",
    "RankingMetricControls",
    "RankingQueryInput",
    "RelevanceInput",
    "UncertaintyControls",
    "measure",
    "parse_measurement_json",
]

_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    from_attributes=True,
    hide_input_in_errors=True,
    populate_by_name=True,
    revalidate_instances="always",
)
_STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_MAX_TEXT_LENGTH = 256
_MIN_SCALE_LEVELS = 2
_BINARY_CLASS_COUNT = 2
_SURROGATE_MIN = 0xD800
_SURROGATE_MAX = 0xDFFF
_SUMMARY_ULPS: Final[int] = 32
_SUMMARY_TOLERANCE: Final[float] = _SUMMARY_ULPS * math.ulp(1.0)
_RANKING_SUMMARY_FIELDS: Final[tuple[str, ...]] = (
    "precision_at_k",
    "recall_at_k",
    "f1_at_k",
    "ndcg_at_k",
    "reciprocal_rank",
    "average_precision",
)
_RANKING_REPORT_FIELDS: Final[tuple[str, ...]] = (
    "mean_precision_at_k",
    "mean_recall_at_k",
    "mean_f1_at_k",
    "mean_ndcg_at_k",
    "mrr",
    "mean_average_precision",
)
_OptionalBool = bool | None
_OptionalExtra = ExtraValues | None
_PythonValidationOptions = tuple[
    _OptionalBool,
    _OptionalExtra,
    _OptionalBool,
    object | None,
    _OptionalBool,
    _OptionalBool,
]
_JsonValidationOptions = tuple[
    _OptionalBool, _OptionalExtra, object | None, _OptionalBool, _OptionalBool
]


def _converted_float(value: int | float, error: type[Exception]) -> float:
    try:
        return float(value)
    except OverflowError:
        raise error from None


def _finite(value: object) -> float:
    if isinstance(value, bool):
        raise InvalidScoreRequest
    if not isinstance(value, (int, float)):
        raise InvalidScoreRequest
    number = _converted_float(value, InvalidScoreRequest)
    if not math.isfinite(number):
        raise InvalidScoreRequest
    return 0.0 if number == 0.0 else number


def _probability(value: object) -> float:
    number = _finite(value)
    if not 0.0 <= number <= 1.0:
        raise InvalidScoreRequest
    return number


def _binary_label(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise InvalidScoreRequest
    return value


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidSettings
    return value


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidSettings
    return value


def _confidence(value: object) -> float:
    number = _finite(value)
    if not 0.0 < number < 1.0:
        raise InvalidSettings
    return number


def _identifier(value: object) -> str:
    if not isinstance(value, str) or len(value) > _MAX_TEXT_LENGTH:
        raise ContractValidationError
    if _STABLE_ID.fullmatch(value) is None:
        raise ContractValidationError
    return value


def _safe_text(value: object) -> str:
    if not isinstance(value, str):
        raise ContractValidationError
    if not value or len(value) > _MAX_TEXT_LENGTH:
        raise ContractValidationError
    if _contains_surrogate(value):
        raise ContractValidationError
    return value


def _contains_surrogate(value: str) -> bool:
    return any(_SURROGATE_MIN <= ord(character) <= _SURROGATE_MAX for character in value)


def _require_unique_ranking(values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise InvalidRankingRequest


def _require_relevant(judgments: tuple[RelevanceInput, ...]) -> None:
    if not any(row.gain > 0.0 for row in judgments):
        raise EmptyRelevantSet


def _require_unique_agreement(values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise InvalidAgreementRequest


def _require_known_ratings(values: tuple[str, ...], scale: tuple[str, ...]) -> None:
    if not set(values) <= set(scale):
        raise InvalidAgreementRequest


def _require_workload(sample_count: int, resamples: int) -> None:
    if sample_count * resamples > MAX_BOOTSTRAP_WORK_CELLS:
        raise InvalidSettings


def _require_result_workload(sample_count: int, resamples: int, error: type[AssayError]) -> None:
    if sample_count * resamples > MAX_BOOTSTRAP_WORK_CELLS:
        raise error


type _Probability = Annotated[float, BeforeValidator(_probability)]
type _Finite = Annotated[float, BeforeValidator(_finite)]
type _BinaryLabel = Annotated[int, BeforeValidator(_binary_label)]
type _PositiveInt = Annotated[int, BeforeValidator(_positive_int)]
type _NonnegativeInt = Annotated[int, BeforeValidator(_nonnegative_int)]
type _Confidence = Annotated[float, BeforeValidator(_confidence)]
type _Identifier = Annotated[str, BeforeValidator(_identifier)]
type _SafeText = Annotated[str, BeforeValidator(_safe_text)]


def _result_json(data: str | bytes | bytearray, error: type[AssayError]) -> Mapping[str, object]:
    decoded = decode_json(data, error)
    if not isinstance(decoded, Mapping):
        raise error
    return cast(Mapping[str, object], decoded)


class _MeasurementModel(BaseModel):
    model_config = _CONFIG
    _error: ClassVar[type[AssayError]] = ContractValidationError

    def __init__(self, **data: object) -> None:
        try:
            super().__init__(**data)
        except (ValidationError, OverflowError):
            raise self._error from None

    @classmethod
    def model_validate(
        cls,
        obj: object,
        *,
        strict: _OptionalBool = None,
        extra: _OptionalExtra = None,
        from_attributes: _OptionalBool = None,
        context: object | None = None,
        by_alias: _OptionalBool = None,
        by_name: _OptionalBool = None,
    ) -> Self:
        options = (strict, extra, from_attributes, context, by_alias, by_name)
        return cls._validate_python(obj, options)

    @classmethod
    def _validate_python(cls, obj: object, options: _PythonValidationOptions) -> Self:
        strict, extra, from_attributes, context, by_alias, by_name = options
        try:
            return super().model_validate(
                obj,
                strict=strict,
                extra=extra,
                from_attributes=from_attributes,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except (ValidationError, OverflowError):
            raise cls._error from None

    @classmethod
    def model_validate_json(
        cls,
        data: str | bytes | bytearray,
        *,
        strict: _OptionalBool = None,
        extra: _OptionalExtra = None,
        context: object | None = None,
        by_alias: _OptionalBool = None,
        by_name: _OptionalBool = None,
    ) -> Self:
        options = (strict, extra, context, by_alias, by_name)
        return cls._validate_decoded_json(data, options)

    @classmethod
    def _validate_decoded_json(
        cls, data: str | bytes | bytearray, options: _JsonValidationOptions
    ) -> Self:
        strict, extra, context, by_alias, by_name = options
        decoded = _result_json(data, cls._error)
        return cls.model_validate(
            decoded,
            strict=strict,
            extra=extra,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )

    def model_copy(self, *, update: Mapping[str, object] | None = None, deep: bool = False) -> Self:
        candidate = super().model_copy(update=update, deep=deep)
        return type(self).model_validate(candidate)

    @model_serializer(mode="wrap")
    def _serialize_validated(self, handler: SerializerFunctionWrapHandler) -> object:
        return handler(type(self).model_validate(self))


class UncertaintyControls(_MeasurementModel):
    """Explicit controls shared by ordinal agreement requests."""

    _error = InvalidSettings
    min_samples: Annotated[_PositiveInt, Field(le=MAX_ITEMS)] = 30
    bootstrap_resamples: Annotated[_PositiveInt, Field(le=MAX_BOOTSTRAP_RESAMPLES)] = 9999
    confidence_level: _Confidence = 0.95
    bootstrap_seed: Annotated[_NonnegativeInt, Field(le=MAX_SEED)] = 12345


class BinaryMetricControls(_MeasurementModel):
    """Explicit binary calibration and uncertainty controls."""

    _error = InvalidSettings
    min_samples: Annotated[_PositiveInt, Field(le=MAX_ITEMS)] = 30
    bootstrap_resamples: Annotated[_PositiveInt, Field(le=MAX_BOOTSTRAP_RESAMPLES)] = 9999
    confidence_level: _Confidence = 0.95
    ece_bins: Annotated[_PositiveInt, Field(le=MAX_CALIBRATION_BINS)] = 15
    bootstrap_seed: Annotated[_NonnegativeInt, Field(le=MAX_SEED)] = 12345


class RankingMetricControls(_MeasurementModel):
    """Explicit ranking uncertainty controls."""

    _error = InvalidSettings
    min_samples: Annotated[_PositiveInt, Field(le=MAX_ITEMS)] = 30
    bootstrap_resamples: Annotated[_PositiveInt, Field(le=MAX_BOOTSTRAP_RESAMPLES)] = 9999
    confidence_level: _Confidence = 0.95
    bootstrap_seed: Annotated[_NonnegativeInt, Field(le=MAX_SEED)] = 12345


class RelevanceInput(_MeasurementModel):
    """One bounded graded relevance judgment."""

    _error = InvalidRankingRequest
    doc_id: _SafeText
    gain: Annotated[_Finite, Field(ge=0.0, le=MAX_RELEVANCE_GAIN)] = 1.0

    @model_validator(mode="after")
    def _require_integer_gain(self) -> RelevanceInput:
        if self.gain != int(self.gain):
            raise InvalidRankingRequest
        return self


class RankingQueryInput(_MeasurementModel):
    """One typed ranked list and its complete judgment set."""

    _error = InvalidRankingRequest
    query: _SafeText
    judgments: Annotated[tuple[RelevanceInput, ...], Field(min_length=1, max_length=MAX_ITEMS)]
    ranked: Annotated[tuple[_SafeText, ...], Field(min_length=1, max_length=MAX_ITEMS)]

    @model_validator(mode="after")
    def _require_distinct_documents(self) -> RankingQueryInput:
        judged = tuple(row.doc_id for row in self.judgments)
        _require_unique_ranking(judged)
        _require_unique_ranking(self.ranked)
        _require_relevant(self.judgments)
        return self


class OrdinalRating(_MeasurementModel):
    """One item and the two declared ordinal ratings."""

    _error = InvalidAgreementRequest
    item: _SafeText
    rater_a: _SafeText
    rater_b: _SafeText


class BinaryMeasurementRequest(_MeasurementModel):
    """Classification, calibration, and accuracy-interval inputs."""

    _error = InvalidScoreRequest
    metric: Literal["binary"]
    metric_version: _Identifier
    y_true: Annotated[tuple[_BinaryLabel, ...], Field(min_length=1, max_length=MAX_ITEMS)]
    y_score: Annotated[tuple[_Probability, ...], Field(min_length=1, max_length=MAX_ITEMS)]
    threshold: _Probability = 0.5
    controls: BinaryMetricControls = BinaryMetricControls()

    @model_validator(mode="after")
    def _require_binary_shape(self) -> BinaryMeasurementRequest:
        if len(self.y_true) != len(self.y_score):
            raise InvalidScoreRequest
        if len(set(self.y_true)) != _BINARY_CLASS_COUNT:
            raise InvalidScoreRequest
        _require_workload(len(self.y_true), self.controls.bootstrap_resamples)
        return self


class RankingMeasurementRequest(_MeasurementModel):
    """Ranked-retrieval inputs with a declared cut-off."""

    _error = InvalidRankingRequest
    metric: Literal["ranking"]
    metric_version: _Identifier
    queries: Annotated[tuple[RankingQueryInput, ...], Field(min_length=1, max_length=MAX_ITEMS)]
    k: Annotated[_PositiveInt, Field(le=MAX_RANKING_K)] = 10
    controls: RankingMetricControls = RankingMetricControls()

    @model_validator(mode="after")
    def _require_ranking_workload(self) -> Self:
        _require_workload(len(self.queries), self.controls.bootstrap_resamples)
        return self


class AgreementMeasurementRequest(_MeasurementModel):
    """Ordinal inter-rater inputs with a declared scale."""

    _error = InvalidAgreementRequest
    metric: Literal["agreement"]
    metric_version: _Identifier
    scale: Annotated[
        tuple[_SafeText, ...], Field(min_length=_MIN_SCALE_LEVELS, max_length=MAX_SCALE_LEVELS)
    ]
    ratings: Annotated[tuple[OrdinalRating, ...], Field(min_length=1, max_length=MAX_ITEMS)]
    controls: UncertaintyControls = UncertaintyControls()

    @model_validator(mode="after")
    def _require_ordinal_shape(self) -> AgreementMeasurementRequest:
        items = tuple(row.item for row in self.ratings)
        values = tuple(value for row in self.ratings for value in (row.rater_a, row.rater_b))
        _require_unique_agreement(self.scale)
        _require_unique_agreement(items)
        _require_known_ratings(values, self.scale)
        _require_workload(len(self.ratings), self.controls.bootstrap_resamples)
        return self


type MeasurementRequest = Annotated[
    BinaryMeasurementRequest | RankingMeasurementRequest | AgreementMeasurementRequest,
    Field(discriminator="metric"),
]


def _proof_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError
    if not isinstance(value, (int, float)):
        raise ValueError
    number = _converted_float(value, ValueError)
    if not math.isfinite(number):
        raise ValueError
    return 0.0 if number == 0.0 else number


def _proof_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError
    return value


def _proof_text(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT_LENGTH:
        raise ValueError
    if _contains_surrogate(value):
        raise ValueError
    return value


type _ProofFloat = Annotated[float, BeforeValidator(_proof_float)]
type _ProofProbability = Annotated[_ProofFloat, Field(ge=0.0, le=1.0)]
type _ProofSignedUnit = Annotated[_ProofFloat, Field(ge=-1.0, le=1.0)]
type _ProofCount = Annotated[int, BeforeValidator(_proof_int), Field(ge=0, le=MAX_ITEMS)]
type _ProofPositiveCount = Annotated[int, BeforeValidator(_proof_int), Field(ge=1, le=MAX_ITEMS)]
type _ProofText = Annotated[str, BeforeValidator(_proof_text)]


class _ProofModel(BaseModel):
    model_config = _CONFIG


class _IntervalProof(_ProofModel):
    kind: Literal["interval"]
    point: _ProofProbability
    low: _ProofProbability
    high: _ProofProbability

    @model_validator(mode="after")
    def _require_ordered_bounds(self) -> Self:
        if not self.low <= self.point <= self.high:
            raise ValueError
        return self


class _AbstentionProof(_ProofModel):
    kind: Literal["abstention"]
    reason: _ProofText
    n_samples: _ProofCount
    min_samples: _ProofPositiveCount

    @model_validator(mode="after")
    def _require_honest_floor(self) -> Self:
        if self.n_samples >= self.min_samples:
            raise ValueError
        return self


type _EstimateProof = Annotated[
    _IntervalProof | _AbstentionProof,
    Field(discriminator="kind"),
]


class _CountsProof(_ProofModel):
    true_positives: _ProofCount
    false_positives: _ProofCount
    true_negatives: _ProofCount
    false_negatives: _ProofCount

    @model_validator(mode="after")
    def _require_population(self) -> Self:
        if not 0 < _count_total(self) <= MAX_ITEMS:
            raise ValueError
        return self


def _count_total(counts: _CountsProof) -> int:
    return sum(
        (
            counts.true_positives,
            counts.false_positives,
            counts.true_negatives,
            counts.false_negatives,
        )
    )


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _harmonic(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)


def _classification_expected(counts: _CountsProof) -> tuple[float, ...]:
    precision = _ratio(counts.true_positives, counts.true_positives + counts.false_positives)
    recall = _ratio(counts.true_positives, counts.true_positives + counts.false_negatives)
    accuracy = (counts.true_positives + counts.true_negatives) / _count_total(counts)
    actual_positives = counts.true_positives + counts.false_negatives
    false_negative_rate = _ratio(counts.false_negatives, actual_positives)
    return accuracy, precision, recall, _harmonic(precision, recall), false_negative_rate


class _ClassificationProof(_ProofModel):
    accuracy: _ProofProbability
    precision: _ProofProbability
    recall: _ProofProbability
    f1: _ProofProbability
    pr_auc: _ProofProbability
    roc_auc: _ProofProbability
    counts: _CountsProof
    false_negative_rate: _ProofProbability

    @model_validator(mode="after")
    def _require_count_rates(self) -> Self:
        observed = (self.accuracy, self.precision, self.recall, self.f1, self.false_negative_rate)
        if not _summaries_match(observed, _classification_expected(self.counts)):
            raise ValueError
        return self


class _ReliabilityBinProof(_ProofModel):
    mean_predicted: _ProofProbability
    fraction_positive: _ProofProbability
    count: _ProofPositiveCount


class _CalibrationProof(_ProofModel):
    ece: _ProofProbability
    brier: _ProofProbability
    bins: Annotated[
        tuple[_ReliabilityBinProof, ...], Field(min_length=1, max_length=MAX_CALIBRATION_BINS)
    ]


def _expected_ece(calibration: _CalibrationProof, total: int) -> float:
    return sum(
        row.count / total * abs(row.mean_predicted - row.fraction_positive)
        for row in calibration.bins
    )


def _summary_matches(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=_SUMMARY_TOLERANCE)


def _summaries_match(observed: tuple[float, ...], expected: tuple[float, ...]) -> bool:
    pairs = zip(observed, expected, strict=True)
    return all(_summary_matches(actual, wanted) for actual, wanted in pairs)


def _positive_population(calibration: _CalibrationProof) -> float:
    return math.fsum(row.fraction_positive * row.count for row in calibration.bins)


def _require_calibration_total(report: _BinaryReportProof, total: int) -> None:
    if sum(row.count for row in report.calibration.bins) != total:
        raise ValueError


def _require_calibration_positives(report: _BinaryReportProof) -> None:
    counts = report.classification.counts
    actual_positives = counts.true_positives + counts.false_negatives
    if not _summary_matches(_positive_population(report.calibration), actual_positives):
        raise ValueError


def _require_calibration_ece(report: _BinaryReportProof, total: int) -> None:
    if report.calibration.ece != _expected_ece(report.calibration, total):
        raise ValueError


class _BinaryReportProof(_ProofModel):
    classification: _ClassificationProof
    calibration: _CalibrationProof
    accuracy_interval: _EstimateProof

    @model_validator(mode="after")
    def _require_same_population(self) -> Self:
        total = _count_total(self.classification.counts)
        _require_calibration_total(self, total)
        _require_calibration_positives(self)
        _require_calibration_ece(self, total)
        return self


class _QueryProof(_ProofModel):
    query: _ProofText
    precision_at_k: _ProofProbability
    recall_at_k: _ProofProbability
    f1_at_k: _ProofProbability
    ndcg_at_k: _ProofProbability
    reciprocal_rank: _ProofProbability
    average_precision: _ProofProbability

    @model_validator(mode="after")
    def _require_f1_summary(self) -> Self:
        if not _summary_matches(self.f1_at_k, _harmonic(self.precision_at_k, self.recall_at_k)):
            raise ValueError
        return self


def _mean(values: tuple[float, ...]) -> float:
    return math.fsum(values) / len(values)


def _query_values(rows: tuple[_QueryProof, ...], field: str) -> tuple[float, ...]:
    return tuple(cast(float, getattr(row, field)) for row in rows)


def _ranking_expected(rows: tuple[_QueryProof, ...]) -> tuple[float, ...]:
    return tuple(_mean(_query_values(rows, field)) for field in _RANKING_SUMMARY_FIELDS)


def _ranking_observed(report: _RankingReportProof) -> tuple[float, ...]:
    return tuple(cast(float, getattr(report, field)) for field in _RANKING_REPORT_FIELDS)


class _RankingReportProof(_ProofModel):
    k: Annotated[_ProofPositiveCount, Field(le=MAX_RANKING_K)]
    n_queries: _ProofPositiveCount
    per_query: Annotated[tuple[_QueryProof, ...], Field(min_length=1, max_length=MAX_ITEMS)]
    mean_precision_at_k: _ProofProbability
    mean_recall_at_k: _ProofProbability
    mean_f1_at_k: _ProofProbability
    mean_ndcg_at_k: _ProofProbability
    mrr: _ProofProbability
    mean_average_precision: _ProofProbability
    ndcg_interval: _EstimateProof

    @model_validator(mode="after")
    def _require_query_population(self) -> Self:
        if self.n_queries != len(self.per_query):
            raise ValueError
        if not _summaries_match(_ranking_observed(self), _ranking_expected(self.per_query)):
            raise ValueError
        return self


class _AgreementReportProof(_ProofModel):
    scale: Annotated[
        tuple[_ProofText, ...], Field(min_length=_MIN_SCALE_LEVELS, max_length=MAX_SCALE_LEVELS)
    ]
    n_items: _ProofPositiveCount
    n_exact_matches: _ProofCount
    percent_agreement: _ProofProbability
    weighted_agreement: _ProofProbability
    quadratic_kappa: _ProofSignedUnit | None
    kappa_undefined_reason: _ProofText | None
    kendall_tau_b: _ProofSignedUnit | None
    tau_undefined_reason: _ProofText | None
    weighted_agreement_interval: _EstimateProof

    @model_validator(mode="after")
    def _require_agreement_population(self) -> Self:
        if len(self.scale) != len(set(self.scale)) or self.n_exact_matches > self.n_items:
            raise ValueError
        if self.percent_agreement != self.n_exact_matches / self.n_items:
            raise ValueError
        _require_reason_pair(self.quadratic_kappa, self.kappa_undefined_reason)
        _require_reason_pair(self.kendall_tau_b, self.tau_undefined_reason)
        return self


def _require_reason_pair(value: float | None, reason: str | None) -> None:
    if (value is None) != (reason is not None):
        raise ValueError


def _prove(data: object, proof: type[_ProofModel], error: type[AssayError]) -> None:
    try:
        proof.model_validate(data)
    except (ValidationError, OverflowError):
        raise error from None


def _field(data: object, name: str) -> object:
    if isinstance(data, Mapping):
        return data.get(name)
    return getattr(data, name, None)


def _require_estimate(
    estimate: Estimate,
    count: int,
    minimum: int,
    point: float,
    error: type[AssayError],
) -> None:
    if estimate.kind == "abstention":
        _require_abstention(estimate, count, minimum, error)
        return
    _require_interval(estimate, count, minimum, point, error)


def _require_abstention(
    estimate: Abstention, count: int, minimum: int, error: type[AssayError]
) -> None:
    if count >= minimum or estimate.n_samples != count or estimate.min_samples != minimum:
        raise error


def _require_interval(
    estimate: Interval,
    count: int,
    minimum: int,
    point: float,
    error: type[AssayError],
) -> None:
    if count < minimum or estimate.point != point:
        raise error


class BinaryResultControls(_MeasurementModel):
    _error = InvalidScoreRequest
    threshold: _Probability
    min_samples: Annotated[_PositiveInt, Field(le=MAX_ITEMS)]
    bootstrap_resamples: Annotated[_PositiveInt, Field(le=MAX_BOOTSTRAP_RESAMPLES)]
    confidence_level: _Confidence
    ece_bins: Annotated[_PositiveInt, Field(le=MAX_CALIBRATION_BINS)]
    bootstrap_seed: Annotated[_NonnegativeInt, Field(le=MAX_SEED)]


class RankingResultControls(_MeasurementModel):
    _error = InvalidRankingRequest
    k: Annotated[_PositiveInt, Field(le=MAX_RANKING_K)]
    min_samples: Annotated[_PositiveInt, Field(le=MAX_ITEMS)]
    bootstrap_resamples: Annotated[_PositiveInt, Field(le=MAX_BOOTSTRAP_RESAMPLES)]
    confidence_level: _Confidence
    bootstrap_seed: Annotated[_NonnegativeInt, Field(le=MAX_SEED)]


class AgreementResultControls(_MeasurementModel):
    _error = InvalidAgreementRequest
    min_samples: Annotated[_PositiveInt, Field(le=MAX_ITEMS)]
    bootstrap_resamples: Annotated[_PositiveInt, Field(le=MAX_BOOTSTRAP_RESAMPLES)]
    confidence_level: _Confidence
    bootstrap_seed: Annotated[_NonnegativeInt, Field(le=MAX_SEED)]


class BinaryMeasurementReport(_MeasurementModel):
    _error = InvalidScoreRequest
    classification: ClassificationScores
    calibration: CalibrationReport
    accuracy_interval: Estimate

    @model_validator(mode="before")
    @classmethod
    def _prove_report(cls, data: object) -> object:
        _prove(data, _BinaryReportProof, InvalidScoreRequest)
        return data


class BinaryMeasurementResult(_MeasurementModel):
    _error = InvalidScoreRequest
    schema_version: Literal["assay.measurement/v1"] = Field(
        default="assay.measurement/v1", alias="schema"
    )
    metric: Literal["binary"]
    metric_version: _Identifier
    controls: BinaryResultControls
    report: BinaryMeasurementReport

    @model_validator(mode="after")
    def _require_binary_invariants(self) -> Self:
        counts = self.report.classification.counts
        count = sum(vars(counts).values())
        _require_estimate(
            self.report.accuracy_interval,
            count,
            self.controls.min_samples,
            self.report.classification.accuracy,
            InvalidScoreRequest,
        )
        if len(self.report.calibration.bins) > self.controls.ece_bins:
            raise InvalidScoreRequest
        _require_result_workload(count, self.controls.bootstrap_resamples, InvalidScoreRequest)
        return self


class RankingMeasurementResult(_MeasurementModel):
    _error = InvalidRankingRequest
    schema_version: Literal["assay.measurement/v1"] = Field(
        default="assay.measurement/v1", alias="schema"
    )
    metric: Literal["ranking"]
    metric_version: _Identifier
    controls: RankingResultControls
    report: RankingReport

    @model_validator(mode="before")
    @classmethod
    def _prove_report(cls, data: object) -> object:
        _prove(_field(data, "report"), _RankingReportProof, InvalidRankingRequest)
        return data

    @model_validator(mode="after")
    def _require_ranking_invariants(self) -> Self:
        if self.controls.k != self.report.k:
            raise InvalidRankingRequest
        _require_estimate(
            self.report.ndcg_interval,
            self.report.n_queries,
            self.controls.min_samples,
            self.report.mean_ndcg_at_k,
            InvalidRankingRequest,
        )
        _require_result_workload(
            self.report.n_queries, self.controls.bootstrap_resamples, InvalidRankingRequest
        )
        return self


class AgreementMeasurementResult(_MeasurementModel):
    _error = InvalidAgreementRequest
    schema_version: Literal["assay.measurement/v1"] = Field(
        default="assay.measurement/v1", alias="schema"
    )
    metric: Literal["agreement"]
    metric_version: _Identifier
    controls: AgreementResultControls
    report: AgreementReport

    @model_validator(mode="before")
    @classmethod
    def _prove_report(cls, data: object) -> object:
        _prove(_field(data, "report"), _AgreementReportProof, InvalidAgreementRequest)
        return data

    @model_validator(mode="after")
    def _require_agreement_invariants(self) -> Self:
        _require_estimate(
            self.report.weighted_agreement_interval,
            self.report.n_items,
            self.controls.min_samples,
            self.report.weighted_agreement,
            InvalidAgreementRequest,
        )
        _require_result_workload(
            self.report.n_items, self.controls.bootstrap_resamples, InvalidAgreementRequest
        )
        return self


type MeasurementResult = Annotated[
    BinaryMeasurementResult | RankingMeasurementResult | AgreementMeasurementResult,
    Field(discriminator="metric"),
]


def _settings(
    controls: UncertaintyControls | BinaryMetricControls | RankingMetricControls,
) -> AssaySettings:
    data = controls.model_dump()
    data.setdefault("ece_bins", 15)
    data.setdefault("ranking_k", 10)
    return AssaySettings(**data)


def _binary_controls(request: BinaryMeasurementRequest) -> BinaryResultControls:
    return BinaryResultControls(threshold=request.threshold, **request.controls.model_dump())


def _ranking_controls(request: RankingMeasurementRequest) -> RankingResultControls:
    return RankingResultControls(k=request.k, **request.controls.model_dump())


def _agreement_controls(request: AgreementMeasurementRequest) -> AgreementResultControls:
    return AgreementResultControls(**request.controls.model_dump())


def _ranking_query(query: RankingQueryInput) -> RankedQuery:
    judgments = tuple(
        RelevanceJudgment(doc_id=row.doc_id, gain=row.gain) for row in query.judgments
    )
    return RankedQuery(query=query.query, judgments=judgments, ranked=query.ranked)


def _ordinal_rating(rating: OrdinalRating) -> ItemRating:
    return ItemRating(item=rating.item, rater_a=rating.rater_a, rater_b=rating.rater_b)


def _accuracy_interval(request: BinaryMeasurementRequest) -> Estimate:
    samples = correctness(request.y_true, request.y_score, threshold=request.threshold)
    return mean_interval(
        samples,
        min_samples=request.controls.min_samples,
        n_resamples=request.controls.bootstrap_resamples,
        confidence_level=request.controls.confidence_level,
        seed=request.controls.bootstrap_seed,
    )


def _binary_report(request: BinaryMeasurementRequest) -> BinaryMeasurementReport:
    scores = binary_scores(request.y_true, request.y_score, threshold=request.threshold)
    calibration = calibration_report(
        request.y_true, request.y_score, n_bins=request.controls.ece_bins
    )
    return BinaryMeasurementReport(
        classification=scores,
        calibration=calibration,
        accuracy_interval=_accuracy_interval(request),
    )


def _measure_binary(request: BinaryMeasurementRequest) -> BinaryMeasurementResult:
    return BinaryMeasurementResult(
        metric="binary",
        metric_version=request.metric_version,
        controls=_binary_controls(request),
        report=_binary_report(request),
    )


def _measure_ranking(request: RankingMeasurementRequest) -> RankingMeasurementResult:
    queries = tuple(_ranking_query(query) for query in request.queries)
    report = ranking_report(queries, settings=_settings(request.controls), k=request.k)
    return RankingMeasurementResult(
        metric="ranking",
        metric_version=request.metric_version,
        controls=_ranking_controls(request),
        report=report,
    )


def _measure_agreement(request: AgreementMeasurementRequest) -> AgreementMeasurementResult:
    ratings = tuple(_ordinal_rating(rating) for rating in request.ratings)
    report = agreement_report(ratings, scale=request.scale, settings=_settings(request.controls))
    return AgreementMeasurementResult(
        metric="agreement",
        metric_version=request.metric_version,
        controls=_agreement_controls(request),
        report=report,
    )


@overload
def measure(request: BinaryMeasurementRequest) -> BinaryMeasurementResult: ...


@overload
def measure(request: RankingMeasurementRequest) -> RankingMeasurementResult: ...


@overload
def measure(request: AgreementMeasurementRequest) -> AgreementMeasurementResult: ...


def measure(request: MeasurementRequest) -> MeasurementResult:
    """Execute one typed family after proving every optional dependency exists."""
    request = _revalidate_request(request)
    require_metrics_extra()
    if request.metric == "binary":
        return _measure_binary(request)
    if request.metric == "ranking":
        return _measure_ranking(request)
    return _measure_agreement(request)


def _revalidate_request(request: MeasurementRequest) -> MeasurementRequest:
    models = (BinaryMeasurementRequest, RankingMeasurementRequest, AgreementMeasurementRequest)
    model = type(request)
    if model not in models:
        raise ContractValidationError
    return model.model_validate(request)


def _decoded(data: str | bytes | bytearray) -> Mapping[str, object]:
    decoded = decode_json(data, ContractValidationError)
    if not isinstance(decoded, Mapping):
        raise ContractValidationError
    return cast(Mapping[str, object], decoded)


def _parse_model(data: Mapping[str, object], model: type[_MeasurementModel]) -> MeasurementRequest:
    try:
        return cast(MeasurementRequest, model.model_validate(data))
    except ValidationError:
        raise model._error from None


def parse_measurement_json(data: str | bytes | bytearray) -> MeasurementRequest:
    """Parse the closed discriminator without importing scientific dependencies."""
    decoded = _decoded(data)
    models: Mapping[str, type[_MeasurementModel]] = {
        "binary": BinaryMeasurementRequest,
        "ranking": RankingMeasurementRequest,
        "agreement": AgreementMeasurementRequest,
    }
    metric = decoded.get("metric")
    if not isinstance(metric, str) or metric not in models:
        raise UnknownMetric
    return _parse_model(decoded, models[metric])
