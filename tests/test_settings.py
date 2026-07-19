from __future__ import annotations

import pytest

from assay.settings import AssaySettings


def test_should_use_documented_defaults_when_no_env() -> None:
    # Given no ASSAY_* environment variables
    # When settings are constructed
    settings = AssaySettings()
    # Then the honesty-relevant defaults hold
    assert settings.min_samples == 30
    assert settings.confidence_level == 0.95
    assert settings.ece_bins == 15


def test_should_override_from_env_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an env override for the sample-size floor
    monkeypatch.setenv("ASSAY_MIN_SAMPLES", "5")
    # When settings are constructed
    settings = AssaySettings()
    # Then the override wins (nothing is hardcoded)
    assert settings.min_samples == 5
