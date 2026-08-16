"""Strict three-family measurement contracts and optional metric dispatch."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Annotated, ClassVar, Literal, cast, overload

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

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
from assay.uncertainty import Estimate, mean_interval

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

_CONFIG = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_MAX_TEXT_LENGTH = 256
_MIN_SCALE_LEVELS = 2
_BINARY_CLASS_COUNT = 2
_SURROGATE_MIN = 0xD800
_SURROGATE_MAX = 0xDFFF


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidScoreRequest
    number = float(value)
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


type _Probability = Annotated[float, BeforeValidator(_probability)]
type _Finite = Annotated[float, BeforeValidator(_finite)]
type _BinaryLabel = Annotated[int, BeforeValidator(_binary_label)]
type _PositiveInt = Annotated[int, BeforeValidator(_positive_int)]
type _NonnegativeInt = Annotated[int, BeforeValidator(_nonnegative_int)]
type _Confidence = Annotated[float, BeforeValidator(_confidence)]
type _Identifier = Annotated[str, BeforeValidator(_identifier)]
type _SafeText = Annotated[str, BeforeValidator(_safe_text)]


class _MeasurementModel(BaseModel):
    model_config = _CONFIG
    _error: ClassVar[type[AssayError]] = ContractValidationError

    def __init__(self, **data: object) -> None:
        try:
            super().__init__(**data)
        except ValidationError:
            raise self._error from None


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
        return self


class RankingMeasurementRequest(_MeasurementModel):
    """Ranked-retrieval inputs with a declared cut-off."""

    _error = InvalidRankingRequest
    metric: Literal["ranking"]
    metric_version: _Identifier
    queries: Annotated[tuple[RankingQueryInput, ...], Field(min_length=1, max_length=MAX_ITEMS)]
    k: Annotated[_PositiveInt, Field(le=MAX_RANKING_K)] = 10
    controls: RankingMetricControls = RankingMetricControls()


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
        return self


type MeasurementRequest = Annotated[
    BinaryMeasurementRequest | RankingMeasurementRequest | AgreementMeasurementRequest,
    Field(discriminator="metric"),
]


class BinaryResultControls(_MeasurementModel):
    threshold: _Probability
    min_samples: _PositiveInt
    bootstrap_resamples: _PositiveInt
    confidence_level: _Confidence
    ece_bins: _PositiveInt
    bootstrap_seed: _NonnegativeInt


class RankingResultControls(_MeasurementModel):
    k: _PositiveInt
    min_samples: _PositiveInt
    bootstrap_resamples: _PositiveInt
    confidence_level: _Confidence
    bootstrap_seed: _NonnegativeInt


class BinaryMeasurementReport(_MeasurementModel):
    classification: ClassificationScores
    calibration: CalibrationReport
    accuracy_interval: Estimate


class BinaryMeasurementResult(_MeasurementModel):
    schema_version: Literal["assay.measurement/v1"] = Field(
        default="assay.measurement/v1", alias="schema"
    )
    metric: Literal["binary"]
    metric_version: _Identifier
    controls: BinaryResultControls
    report: BinaryMeasurementReport


class RankingMeasurementResult(_MeasurementModel):
    schema_version: Literal["assay.measurement/v1"] = Field(
        default="assay.measurement/v1", alias="schema"
    )
    metric: Literal["ranking"]
    metric_version: _Identifier
    controls: RankingResultControls
    report: RankingReport


class AgreementMeasurementResult(_MeasurementModel):
    schema_version: Literal["assay.measurement/v1"] = Field(
        default="assay.measurement/v1", alias="schema"
    )
    metric: Literal["agreement"]
    metric_version: _Identifier
    controls: UncertaintyControls
    report: AgreementReport


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
        controls=request.controls,
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
    require_metrics_extra()
    if request.metric == "binary":
        return _measure_binary(request)
    if request.metric == "ranking":
        return _measure_ranking(request)
    return _measure_agreement(request)


def _decoded(data: str | bytes | bytearray) -> Mapping[str, object]:
    try:
        decoded = json.loads(data)
    except (ValueError, UnicodeDecodeError, TypeError, RecursionError):
        raise ContractValidationError from None
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
