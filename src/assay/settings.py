"""Typed, env-driven configuration. Every tunable knob lives here — nothing is
hardcoded in logic. Override any field with ``ASSAY_<FIELD>`` in the environment
or a ``.env`` file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from assay.errors import MetricsExtraMissing

_SETTINGS_AVAILABLE = False

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings, SettingsConfigDict
else:
    try:
        from pydantic_settings import BaseSettings, SettingsConfigDict

        _SETTINGS_AVAILABLE = True
    except ImportError:
        BaseSettings = object
        SettingsConfigDict = dict


class AssaySettings(BaseSettings):
    """All runtime tunables for Assay, sourced from ``ASSAY_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="ASSAY_", frozen=True)

    def __new__(cls, **_data: object) -> Self:
        if not _SETTINGS_AVAILABLE:
            raise MetricsExtraMissing from None
        return super().__new__(cls)

    min_samples: int = 30
    bootstrap_resamples: int = 9999
    confidence_level: float = 0.95
    ece_bins: int = 15
    bootstrap_seed: int = 12345
    # Default cut-off for the ranked-retrieval metrics (precision@k, recall@k, nDCG@k).
    # 10 is the conventional "first page" depth; a caller may pass its own k per report.
    ranking_k: int = 10
