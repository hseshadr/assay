"""Assay combines heterogeneous measurements into explainable scores."""

from __future__ import annotations

from assay._version import __version__
from assay.contracts import (
    AdditiveRequest,
    AdditiveTerm,
    ClampPolicy,
    Component,
    Direction,
    ExplainedComponent,
    Interval,
    Method,
    MinimumRequest,
    NativeScale,
    Operation,
    ScoreRequest,
    ScoreResult,
    WeightedMeanRequest,
    parse_request,
    parse_request_json,
)
from assay.errors import ContractValidationError
from assay.normalize import normalize

__all__ = [
    "AdditiveRequest",
    "AdditiveTerm",
    "ClampPolicy",
    "Component",
    "ContractValidationError",
    "Direction",
    "ExplainedComponent",
    "Interval",
    "Method",
    "MinimumRequest",
    "NativeScale",
    "Operation",
    "ScoreRequest",
    "ScoreResult",
    "WeightedMeanRequest",
    "__version__",
    "normalize",
    "parse_request",
    "parse_request_json",
]
