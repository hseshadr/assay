from __future__ import annotations

import pytest
from pydantic import ValidationError

from assay.models import CompositeRequest, ScoreRequest, SubScoreInput


def test_should_parse_score_request_from_json() -> None:
    # Given a JSON score request
    raw = '{"metric":"binary","metric_version":"1","y_true":[0,1],"y_score":[0.2,0.8]}'
    # When validated
    request = ScoreRequest.model_validate_json(raw)
    # Then it round-trips into immutable tuples with the default threshold
    assert request.y_true == (0, 1)
    assert request.y_score == (0.2, 0.8)
    assert request.threshold == 0.5


def test_should_reject_unknown_fields() -> None:
    # Given a request with an unexpected field
    raw = '{"metric":"binary","metric_version":"1","y_true":[0,1],"y_score":[0.2,0.8],"x":9}'
    # When validated
    # Then it is rejected (extra="forbid")
    with pytest.raises(ValidationError):
        ScoreRequest.model_validate_json(raw)


def test_should_build_composite_request_with_default_metric() -> None:
    # Given three sub-score inputs
    subs = tuple(
        SubScoreInput(
            name=n,
            value=1.0,
            low=0.9,
            high=1.0,
            scale_min=0.0,
            scale_max=2.0,
            weight=1.0,
        )
        for n in ("a", "b", "c")
    )
    # When a composite request is built without naming the metric
    request = CompositeRequest(metric_version="1", subscores=subs)
    # Then the metric defaults to the composite label
    assert request.metric == "weighted_composite"
    assert len(request.subscores) == 3
