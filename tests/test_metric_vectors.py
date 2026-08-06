"""Shared metric vectors: the cross-language ANSWER contract.

``testdata/vectors/metrics.json`` is replayed here against the Python face and, file
for file and case for case, by ``ts/src/metricVectors.test.ts`` against
``@edgeproc/avow``. Python delegates to ``trec_eval`` (through ``ir_measures``) and
scikit-learn; TypeScript counts the same quantities out against their definitions.
Two implementations of one rule is exactly the arrangement that drifts, so the two
are pinned to a single set of hand-computed answers and a divergence fails CI in
both languages.

Unlike ``canonical.json`` and ``receipts.json``, this file is **not** generated.
Those hold bytes and signatures nobody could author by hand. Every number here was
computed from the metric's definition (the ``hand`` field on each case carries the
arithmetic) and never read back out of the code under test.

*How the confusion cells are pinned.* ``assay.metrics`` on this branch returns
rates, not named cells, so the four cells cannot be asserted against a Python
function directly. They do not need to be: the number of actual positives is
countable straight off ``y_true``, and scikit-learn's recall and accuracy then
determine all four cells uniquely. This file re-derives them from those two sklearn
outputs and requires the result to equal the cells the TypeScript suite asserts. If
either language's cells drift, the derivation stops matching and this test goes red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assay.errors import AssayError
from assay.metrics import binary_scores
from assay.ranking import f1_at_k, mrr, precision_at_k, recall_at_k

_VECTORS = json.loads(Path("testdata/vectors/metrics.json").read_text(encoding="utf-8"))

# The two languages reach these numbers by different routes (a C++ trec_eval binary on
# one side, integer counting on the other), so equality is asserted to a tolerance far
# tighter than any real disagreement and far looser than double-rounding noise.
_TOL = 1e-12


def _approx(value: float) -> object:
    return pytest.approx(value, abs=_TOL, rel=_TOL)


def _raised_code(case: dict, call: object) -> str:
    """Run a refusing call and return the coded error it raised."""
    with pytest.raises(AssayError) as caught:
        call()  # type: ignore[operator]
    assert caught.value.code == case["code"]
    return caught.value.code


@pytest.mark.parametrize("case", _VECTORS["ranking"], ids=lambda c: c["name"])
def test_ranking_vector_replays_to_the_hand_computed_answer(case: dict) -> None:
    # Given one shared ranking vector
    relevant, ranked, k = case["relevant"], case["ranked"], case["k"]
    want = case["expected"]
    # When the Python ranking face scores it
    # Then every metric equals the hand-computed number the TypeScript suite also asserts
    assert precision_at_k(relevant, ranked, k) == _approx(want["precision_at_k"])
    assert recall_at_k(relevant, ranked, k) == _approx(want["recall_at_k"])
    assert f1_at_k(relevant, ranked, k) == _approx(want["f1_at_k"])
    assert mrr(relevant, ranked) == _approx(want["reciprocal_rank"])


@pytest.mark.parametrize("case", _VECTORS["ranking_refusals"], ids=lambda c: c["name"])
def test_ranking_refusal_vector_refuses_with_the_shared_code(case: dict) -> None:
    # Given a shared vector describing an input that must be refused
    relevant, ranked, k = case["relevant"], case["ranked"], case["k"]
    # When the Python face is asked to score it
    # Then it refuses with the same coded error the TypeScript face raises
    _raised_code(case, lambda: precision_at_k(relevant, ranked, k))


def _cells_from_sklearn(case: dict) -> dict[str, int]:
    """Re-derive the four confusion cells from scikit-learn's own outputs.

    ``y_true`` gives the actual-positive and actual-negative counts by counting.
    Recall then fixes ``tp`` (and so ``fn``), and accuracy fixes ``tn`` (and so ``fp``).
    Nothing here reads an assay confusion-count implementation, which is the point:
    this is scikit-learn's answer, expressed as cells."""
    y_true = case["y_true"]
    scores = binary_scores(y_true, case["y_score"], **_threshold_kwargs(case))
    positives, total = sum(y_true), len(y_true)
    true_positives = round(scores.recall * positives)
    true_negatives = round(scores.accuracy * total) - true_positives
    return {
        "true_positives": true_positives,
        "false_negatives": positives - true_positives,
        "true_negatives": true_negatives,
        "false_positives": (total - positives) - true_negatives,
    }


def _threshold_kwargs(case: dict) -> dict[str, float]:
    """A null threshold in the vector means "call it the way a caller with no opinion
    would", so the documented default of 0.5 is exercised rather than restated."""
    threshold = case["threshold"]
    return {} if threshold is None else {"threshold": threshold}


@pytest.mark.parametrize("case", _VECTORS["classification"], ids=lambda c: c["name"])
def test_classification_vector_replays_to_the_hand_computed_rates(case: dict) -> None:
    # Given one shared classification vector
    want = case["expected"]
    # When scikit-learn scores it through assay's Python face
    scores = binary_scores(case["y_true"], case["y_score"], **_threshold_kwargs(case))
    # Then every threshold rate equals the hand-computed number TypeScript also asserts
    assert scores.accuracy == _approx(want["accuracy"])
    assert scores.precision == _approx(want["precision"])
    assert scores.recall == _approx(want["recall"])
    assert scores.f1 == _approx(want["f1"])


@pytest.mark.parametrize("case", _VECTORS["classification"], ids=lambda c: c["name"])
def test_classification_vector_cells_are_the_ones_sklearn_implies(case: dict) -> None:
    # Given one shared classification vector and the cells TypeScript asserts
    want = case["expected"]
    # When the cells are re-derived from scikit-learn's recall and accuracy
    cells = _cells_from_sklearn(case)
    # Then they are the same four numbers, so a transposed cell fails in both languages
    for cell, count in cells.items():
        assert count == want[cell], f"{case['name']}: {cell}"
    assert sum(cells.values()) == len(case["y_true"])


@pytest.mark.parametrize("case", _VECTORS["classification"], ids=lambda c: c["name"])
def test_classification_vector_rates_follow_from_its_cells(case: dict) -> None:
    # Given the cells and rates one shared vector carries
    want = case["expected"]
    positives = want["true_positives"] + want["false_negatives"]
    negatives = want["false_positives"] + want["true_negatives"]
    # When the two rates scikit-learn does not return are computed from the cells
    # Then they are the ones recorded, so FPR and FNR cannot drift from the counts
    assert want["false_positive_rate"] == _approx(want["false_positives"] / negatives)
    assert want["false_negative_rate"] == _approx(want["false_negatives"] / positives)
    # and FNR is the miss rate, which is where a sign flip would show
    assert want["false_negative_rate"] == _approx(1.0 - want["recall"])


@pytest.mark.parametrize("case", _VECTORS["classification_refusals"], ids=lambda c: c["name"])
def test_classification_refusal_vector_is_refused(case: dict) -> None:
    # Given a shared vector describing an input that must be refused
    def call() -> object:
        return binary_scores(case["y_true"], case["y_score"])

    # When the Python face is asked to score it
    if case["code"] is None:
        # Then it refuses uncoded — scikit-learn objects to the multiclass target on
        # Python's behalf, where TypeScript raises its own coded InvalidScoreRequest.
        # The accept/reject boundary is identical; only the class differs. The `match`
        # pins WHY it refused, so a future ValueError from somewhere else cannot pass
        # this test off as the refusal it is asserting.
        with pytest.raises(ValueError, match="multiclass"):
            call()
        return
    # Then it refuses with the same coded error the TypeScript face raises
    _raised_code(case, call)
