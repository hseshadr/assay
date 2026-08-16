"""Dependency failures become stable Assay errors with no private payload."""

from __future__ import annotations

from collections.abc import Callable

import ir_measures
import numpy as np
import pytest
import scipy.stats
import sklearn.calibration
import sklearn.metrics

from assay import _optional
from assay.agreement import quadratic_kappa
from assay.calibration import calibration_report
from assay.errors import (
    AssayError,
    InvalidAgreementRequest,
    InvalidRankingRequest,
    InvalidScoreRequest,
)
from assay.metrics import binary_scores
from assay.ranking import ndcg_at_k
from assay.uncertainty import mean_interval

_PRIVATE = "private-dependency-sentinel"


def _explode(*_args: object, **_kwargs: object) -> object:
    raise RuntimeError(_PRIVATE)


@pytest.fixture(autouse=True)
def clear_optional_caches() -> None:
    _clear_caches()
    yield
    _clear_caches()


def _clear_caches() -> None:
    _optional.load_callable.cache_clear()
    _optional.load_object.cache_clear()
    _optional.load_module.cache_clear()


@pytest.mark.parametrize(
    ("owner", "name", "call", "error_type"),
    [
        (
            sklearn.metrics,
            "accuracy_score",
            lambda: binary_scores([0, 1], [0.1, 0.9]),
            InvalidScoreRequest,
        ),
        (
            sklearn.calibration,
            "calibration_curve",
            lambda: calibration_report([0, 1], [0.1, 0.9], n_bins=2),
            InvalidScoreRequest,
        ),
        (
            ir_measures,
            "calc_aggregate",
            lambda: ndcg_at_k({"private-doc": 1.0}, ["private-doc"], 1),
            InvalidRankingRequest,
        ),
        (
            sklearn.metrics,
            "cohen_kappa_score",
            lambda: quadratic_kappa(["low", "high"], ["low", "high"], scale=("low", "high")),
            InvalidAgreementRequest,
        ),
        (
            scipy.stats,
            "bootstrap",
            lambda: mean_interval(
                [0.0, 1.0], min_samples=1, n_resamples=9, confidence_level=0.9, seed=0
            ),
            InvalidScoreRequest,
        ),
    ],
)
def test_should_translate_dependency_exceptions_without_leaking_inputs(
    monkeypatch: pytest.MonkeyPatch,
    owner: object,
    name: str,
    call: Callable[[], object],
    error_type: type[AssayError],
) -> None:
    monkeypatch.setattr(owner, name, _explode)
    with pytest.raises(error_type) as caught:
        call()
    _assert_redacted(caught.value)


def test_should_reject_a_nonfinite_dependency_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sklearn.metrics, "accuracy_score", lambda *_args, **_kwargs: np.nan)
    with pytest.raises(InvalidScoreRequest) as caught:
        binary_scores([0, 1], [0.1, 0.9])
    _assert_redacted(caught.value)


def _assert_redacted(error: AssayError) -> None:
    surfaces = (str(error), repr(error), repr(error.args), repr(vars(error)))
    assert all(_PRIVATE not in surface and "private-doc" not in surface for surface in surfaces)
    assert error.__context__ is None
    assert error.__cause__ is None
