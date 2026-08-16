"""Bounded runtime settings loaded lazily from ``ASSAY_*`` environment variables."""

from __future__ import annotations

from functools import cache
from typing import Annotated, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, create_model

from assay._optional import call_dependency, dependency_failed, load_callable, load_object
from assay.errors import InvalidSettings, MetricsExtraMissing
from assay.limits import (
    MAX_BOOTSTRAP_RESAMPLES,
    MAX_CALIBRATION_BINS,
    MAX_ITEMS,
    MAX_RANKING_K,
    MAX_SEED,
)


def _reject_bool(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError
    return value


type _SampleCount = Annotated[int, BeforeValidator(_reject_bool), Field(ge=1, le=MAX_ITEMS)]
type _Resamples = Annotated[
    int, BeforeValidator(_reject_bool), Field(ge=1, le=MAX_BOOTSTRAP_RESAMPLES)
]
type _Confidence = Annotated[
    float, BeforeValidator(_reject_bool), Field(gt=0.0, lt=1.0, allow_inf_nan=False)
]
type _Bins = Annotated[int, BeforeValidator(_reject_bool), Field(ge=1, le=MAX_CALIBRATION_BINS)]
type _Seed = Annotated[int, BeforeValidator(_reject_bool), Field(ge=0, le=MAX_SEED)]
type _RankingK = Annotated[int, BeforeValidator(_reject_bool), Field(ge=1, le=MAX_RANKING_K)]


def _create_runtime_model(base: object, config: object) -> type[BaseModel]:
    runtime_base = cast(type[BaseModel], base)
    model = create_model(
        "_RuntimeAssaySettings",
        __base__=runtime_base,
        __config__=cast(ConfigDict, config),
        min_samples=(_SampleCount, _default("min_samples")),
        bootstrap_resamples=(_Resamples, _default("bootstrap_resamples")),
        confidence_level=(_Confidence, _default("confidence_level")),
        ece_bins=(_Bins, _default("ece_bins")),
        bootstrap_seed=(_Seed, _default("bootstrap_seed")),
        ranking_k=(_RankingK, _default("ranking_k")),
    )
    return model


@cache
def _runtime_model() -> type[BaseModel]:
    base = load_object("pydantic_settings", "BaseSettings")
    config_factory = load_callable("pydantic_settings", "SettingsConfigDict")
    config = call_dependency(config_factory, env_prefix="ASSAY_", frozen=True, extra="forbid")
    model = call_dependency(_create_runtime_model, base, config)
    if dependency_failed(config) or dependency_failed(model):
        raise MetricsExtraMissing
    return cast(type[BaseModel], model)


def _settings_values(data: dict[str, object]) -> dict[str, object]:
    loaded = call_dependency(_runtime_model(), **data)
    if dependency_failed(loaded):
        raise InvalidSettings
    return cast(BaseModel, loaded).model_dump()


class AssaySettings(BaseModel):
    """Finite scoring controls, sourced from direct values or ``ASSAY_*`` variables."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_samples: _SampleCount = 30
    bootstrap_resamples: _Resamples = 9999
    confidence_level: _Confidence = 0.95
    ece_bins: _Bins = 15
    bootstrap_seed: _Seed = 12345
    ranking_k: _RankingK = 10

    def __init__(self, **data: object) -> None:
        super().__init__(**_settings_values(data))


def _default(name: str) -> object:
    return AssaySettings.model_fields[name].default
