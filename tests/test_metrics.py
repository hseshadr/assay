from __future__ import annotations

import math

import pytest

from assay.errors import InvalidScoreRequest
from assay.metrics import binary_scores, confusion_counts, correctness, false_negative_rate

# Ten examples: five real positives, five real negatives. At threshold 0.5 the four
# confusion cells all come out DIFFERENT (TP 3, FN 2, FP 1, TN 4), so a test over them
# cannot pass by accident when two cells are read in the wrong order.
_Y_TRUE = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
_Y_SCORE = [0.9, 0.8, 0.7, 0.4, 0.1, 0.6, 0.2, 0.2, 0.1, 0.1]


def test_should_score_perfect_separation_as_one() -> None:
    # Given a perfectly separable binary problem
    y_true = [0, 0, 1, 1]
    y_score = [0.1, 0.2, 0.8, 0.9]
    # When scored at threshold 0.5
    scores = binary_scores(y_true, y_score, threshold=0.5)
    # Then every rank/threshold metric is 1.0
    assert scores.accuracy == 1.0
    assert scores.precision == 1.0
    assert scores.recall == 1.0
    assert scores.f1 == 1.0
    assert scores.pr_auc == pytest.approx(1.0)
    assert scores.roc_auc == pytest.approx(1.0)


def test_should_match_known_roc_auc_of_075() -> None:
    # Given the canonical sklearn ranking example
    y_true = [0, 0, 1, 1]
    y_score = [0.1, 0.4, 0.35, 0.8]
    # When scored
    scores = binary_scores(y_true, y_score)
    # Then ROC-AUC is exactly 0.75
    assert scores.roc_auc == pytest.approx(0.75)


def test_should_return_per_example_correctness_vector() -> None:
    # Given one right and one wrong prediction at threshold 0.5
    y_true = [1, 0]
    y_score = [0.9, 0.9]
    # When computing correctness
    hits = correctness(y_true, y_score, threshold=0.5)
    # Then it is 1.0 for the hit and 0.0 for the miss
    assert hits == (1.0, 0.0)


def test_should_raise_when_only_one_class_present() -> None:
    # Given labels with a single class (AUC undefined)
    with pytest.raises(InvalidScoreRequest):
        binary_scores([1, 1, 1], [0.2, 0.8, 0.5])


@pytest.mark.parametrize("label", [0, 1])
def test_should_allow_one_class_for_confusion_primitives(label: int) -> None:
    # Given labels from only one binary class
    y_true = [label, label, label]
    y_score = [0.1, 0.5, 0.9]
    # When threshold-only primitives are computed
    counts = confusion_counts(y_true, y_score)
    hits = correctness(y_true, y_score)
    # Then no AUC-only both-class rule is applied
    assert sum(vars(counts).values()) == 3
    assert len(hits) == 3


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_should_refuse_nonfinite_classification_numbers(bad: float) -> None:
    # Given a non-finite score or threshold
    with pytest.raises(InvalidScoreRequest) as score_error:
        binary_scores([0, 1], [0.1, bad])
    with pytest.raises(InvalidScoreRequest) as threshold_error:
        confusion_counts([0, 1], [0.1, 0.9], threshold=bad)
    # Then only the stable, value-free request code is exposed
    assert str(score_error.value) == "assay.invalid_request"
    assert str(threshold_error.value) == "assay.invalid_request"


# --------------------------------------------------------------------------------------
# Confusion counts and the false-negative rate — what a screening system actually needs
# --------------------------------------------------------------------------------------


def test_should_count_each_confusion_cell_by_hand() -> None:
    # Given five real positives scored 0.9, 0.8, 0.7, 0.4, 0.1 and five real negatives
    # scored 0.6, 0.2, 0.2, 0.1, 0.1
    # When the confusion cells are counted at threshold 0.5
    counts = confusion_counts(_Y_TRUE, _Y_SCORE, threshold=0.5)
    # Then each cell is the hand count, and no two of them are interchangeable
    assert tuple(vars(counts)) == (
        "true_negatives",
        "false_positives",
        "false_negatives",
        "true_positives",
    )
    assert counts.true_positives == 3  # hand: 0.9, 0.8, 0.7 are positive and predicted 1
    assert counts.false_negatives == 2  # hand: 0.4, 0.1 are positive and predicted 0
    assert counts.false_positives == 1  # hand: 0.6 is negative and predicted 1
    assert counts.true_negatives == 4  # hand: 0.2, 0.2, 0.1, 0.1 negative and predicted 0
    # And they account for every example handed in — nothing was silently dropped
    assert sum(
        (
            counts.true_positives,
            counts.false_negatives,
            counts.false_positives,
            counts.true_negatives,
        )
    ) == len(_Y_TRUE)


def test_should_report_the_miss_rate_as_the_false_negative_rate() -> None:
    # Given the same ten examples
    # When the false-negative rate is taken at threshold 0.5
    # Then it is misses over real positives — NOT misses over everything, and not the
    # false-POSITIVE rate, which is 1/5 here and would look just as plausible
    assert false_negative_rate(_Y_TRUE, _Y_SCORE, threshold=0.5) == pytest.approx(0.4)  # hand: 2/5


def test_should_make_the_false_negative_rate_the_exact_complement_of_recall() -> None:
    # Given the same ten examples scored at three thresholds
    for threshold in (0.15, 0.5, 0.75):
        scores = binary_scores(_Y_TRUE, _Y_SCORE, threshold=threshold)
        fnr = false_negative_rate(_Y_TRUE, _Y_SCORE, threshold=threshold)
        # When recall and FNR are compared
        # Then FNR is exactly 1 - recall. It is named anyway because a 3% miss rate is
        # what a screening system is judged on, and nobody reads it off a recall of 0.97.
        assert fnr == pytest.approx(1.0 - scores.recall)
        assert scores.false_negative_rate == pytest.approx(fnr)


def test_should_drive_the_false_negative_rate_to_zero_when_nothing_is_missed() -> None:
    # Given a threshold low enough that every example is called positive
    # When the FNR is taken
    # Then it is 0.0: no real positive was called negative
    assert false_negative_rate(_Y_TRUE, _Y_SCORE, threshold=0.05) == 0.0
    counts = confusion_counts(_Y_TRUE, _Y_SCORE, threshold=0.05)
    assert (counts.true_positives, counts.false_negatives) == (5, 0)
    assert (counts.false_positives, counts.true_negatives) == (5, 0)


def test_should_carry_the_counts_and_miss_rate_on_the_score_bundle() -> None:
    # Given the same ten examples
    # When they are scored through the existing entry point, unchanged
    scores = binary_scores(_Y_TRUE, _Y_SCORE, threshold=0.5)
    # Then the bundle carries the counts and the miss rate alongside what it always had
    assert scores.counts.true_positives == 3
    assert scores.counts.false_negatives == 2
    assert scores.false_negative_rate == pytest.approx(0.4)
    assert scores.recall == pytest.approx(0.6)  # hand: 3/5, unchanged by the addition


def test_should_refuse_a_label_outside_zero_and_one() -> None:
    # Given a label of 2 in a binary problem
    # When the confusion cells are counted
    # Then it refuses. The confusion matrix is pinned to labels (0, 1) so its orientation
    # can never flip, and sklearn silently DISCARDS any row outside that pinning — the
    # counts would come back looking fine, computed over fewer examples than were passed.
    with pytest.raises(InvalidScoreRequest) as caught:
        confusion_counts([0, 1, 2], [0.1, 0.9, 0.9])
    assert caught.value.code == "assay.invalid_request"
    with pytest.raises(InvalidScoreRequest):
        binary_scores([0, 1, 2], [0.1, 0.9, 0.9])
