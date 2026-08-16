from __future__ import annotations

import pytest

from assay.errors import InvalidSettings
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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_samples": 0},
        {"bootstrap_resamples": True},
        {"bootstrap_resamples": 10**100},
        {"confidence_level": float("nan")},
        {"confidence_level": 1.0},
        {"ece_bins": 10**100},
        {"bootstrap_seed": -1},
        {"ranking_k": True},
    ],
)
def test_should_refuse_invalid_direct_settings_without_leaking_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(InvalidSettings) as caught:
        AssaySettings(**kwargs)
    _assert_private_value_absent(caught.value)


def test_should_refuse_invalid_environment_settings_without_leaking_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "private-settings-sentinel"
    monkeypatch.setenv("ASSAY_MIN_SAMPLES", sentinel)
    with pytest.raises(InvalidSettings) as caught:
        AssaySettings()
    _assert_private_value_absent(caught.value, sentinel)


def _assert_private_value_absent(error: InvalidSettings, sentinel: str = "100000") -> None:
    public = {"code": error.code}
    surfaces = (str(error), repr(error), repr(error.args), repr(vars(error)), repr(public))
    assert error.code == "assay.invalid_settings"
    assert all(sentinel not in surface for surface in surfaces)
    assert error.__context__ is None
    assert error.__cause__ is None
