"""Typed, env-driven configuration. Every tunable knob lives here — nothing is
hardcoded in logic. Override any field with ``ASSAY_<FIELD>`` in the environment
or a ``.env`` file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AssaySettings(BaseSettings):
    """All runtime tunables for Assay, sourced from ``ASSAY_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="ASSAY_", frozen=True)

    min_samples: int = 30
    bootstrap_resamples: int = 9999
    confidence_level: float = 0.95
    ece_bins: int = 15
    bootstrap_seed: int = 12345
    # Default cut-off for the ranked-retrieval metrics (precision@k, recall@k, nDCG@k).
    # 10 is the conventional "first page" depth; a caller may pass its own k per report.
    ranking_k: int = 10
    signing_key_path: str = "signing.key"
    ledger_path: str = "assay-ledger.jsonl"
