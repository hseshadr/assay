"""Literal consumer-oracle replay for every supported composition method."""

from __future__ import annotations

import json
from pathlib import Path

from assay import compose, parse_request

_VECTOR_PATH = Path("testdata/vectors/composition.json")
_EXPECTED_IDS = {
    "northstar_uncapped_weighted",
    "edgereco_recommendation",
    "amlfilter_match_confidence",
    "almamesh_domain_strength_forward_tie",
    "almamesh_domain_strength_reverse_tie",
}
_PII_SENTINEL = "PII-SENTINEL-ALICE"


def _vectors() -> list[dict[str, object]]:
    loaded = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    assert all(isinstance(row, dict) for row in loaded)
    return loaded


def _by_id() -> dict[str, dict[str, object]]:
    return {str(row["id"]): row for row in _vectors()}


def test_should_ship_every_named_consumer_oracle_without_personal_data() -> None:
    # Given the committed cross-consumer composition vectors
    vectors = _vectors()
    # When their identities and serialized bytes are inspected
    identifiers = {str(row["id"]) for row in vectors}
    serialized = json.dumps(vectors, ensure_ascii=False)
    # Then the exact intended set is present and contains no private fixture data
    assert identifiers == _EXPECTED_IDS
    assert _PII_SENTINEL not in serialized
    assert all("source" in row and "consumer" in row for row in vectors)


def test_should_replay_every_literal_consumer_result_exactly() -> None:
    # Given expected results authored from existing consumer formulas
    for vector in _vectors():
        request = parse_request(vector["request"])
        # When the literal request is composed by Assay
        actual = compose(request).model_dump(mode="json")
        # Then every score, explanation, selection, interval, and hash is exact
        assert actual == vector["expected"]


def test_should_keep_northstar_hard_caps_outside_uncapped_arithmetic() -> None:
    # Given Northstar's score-only conformance case
    vector = _by_id()["northstar_uncapped_weighted"]
    # When its scope metadata is inspected
    # Then the fixture states that policy caps and evidence grading remain external
    assert vector["native_score"] == 92
    assert vector["scope"] == (
        "uncapped arithmetic only; hard caps and evidence grading stay external"
    )


def test_should_keep_edgereco_additive_score_distinct_from_weighted_mean() -> None:
    # Given EdgeReco's ordered contribution formula and a literal normalized-mean counterexample
    vector = _by_id()["edgereco_recommendation"]
    expected = vector["expected"]
    assert isinstance(expected, dict)
    # When the two values are compared
    # Then repetition subtraction remains additive rather than silently averaged
    assert expected["score"] == 0.3600000000000001
    assert expected["score"] != vector["normalized_weighted_mean_counterexample"]


def test_should_keep_aml_match_confidence_separate_from_both_risk_concepts() -> None:
    # Given AML Filter's numeric match-confidence fixture
    vector = _by_id()["amlfilter_match_confidence"]
    request = vector["request"]
    assert isinstance(request, dict)
    terms = request["terms"]
    assert isinstance(terms, list)
    # When its declared terms and exclusions are inspected
    identifiers = {str(term["id"]) for term in terms if isinstance(term, dict)}
    # Then source-category risk and analyst KYC risk are not score inputs
    assert vector["excluded_concerns"] == ["source_category_risk", "analyst_kyc_risk"]
    assert identifiers.isdisjoint({"risk_category", "source_category_risk", "analyst_kyc_risk"})


def test_should_keep_almamesh_tie_selection_in_declared_order() -> None:
    # Given the same tied axes in opposite declaration order
    vectors = _by_id()
    forward = vectors["almamesh_domain_strength_forward_tie"]["expected"]
    reverse = vectors["almamesh_domain_strength_reverse_tie"]["expected"]
    assert isinstance(forward, dict)
    assert isinstance(reverse, dict)
    # When their explicit selected IDs are compared
    # Then first occurrence wins even though the lexical order points the other way
    assert forward["selected_component_id"] == "shadbala_pct"
    assert reverse["selected_component_id"] == "sav_pct"
    assert forward["score"] == reverse["score"] == 0.6
