"""The agreement face, pinned to hand-computed worked examples.

Every expected number in this file was computed by hand from the statistic's definition
(the ``# hand:`` comments show the arithmetic), never read back out of the code under
test. A test that asserts whatever the implementation happens to return measures shape,
not property, and would stay green through the exact bugs this module exists to catch.

The arithmetic, once, so the ``# hand:`` comments are readable. Bands sit at positions
0, 1, 2 on the declared scale. The quadratic *disagreement* weight between two bands is
``d(i, j) = ((i - j) / (L - 1)) ** 2`` — 0 for a match, 0.25 for adjacent on a 3-band
scale, 1.0 for opposite ends. Then::

    quadratic kappa = 1 - sum(d * observed) / sum(d * expected)

where ``observed`` is the joint proportion table and ``expected`` is the outer product
of the two raters' marginals — what they would have produced by rating independently.
"""

from __future__ import annotations

import numpy as np
import pytest

from assay.agreement import (
    agreement_report,
    kendall_tau_b,
    percent_agreement,
    quadratic_kappa,
    weighted_agreement,
)
from assay.errors import InvalidAgreementRequest
from assay.models import ItemRating
from assay.settings import AssaySettings
from assay.uncertainty import Abstention, Interval

# The ordered band scale almamesh grades on. Weakest first — the ORDER is the
# measurement, and `sorted()` would put it in a completely different order.
_SCALE = ("weak", "moderate", "strong")

# ---------------------------------------------------------------------------------
# Three worked rating sets, reused throughout.
# ---------------------------------------------------------------------------------

# SKEW: 20 items, both raters call almost everything "weak". They match on 15 of 20 —
# three quarters — but almost all of that is what two raters who both love "weak" would
# have produced by chance.
_SKEW_A = ["weak"] * 18 + ["strong"] * 2
_SKEW_B = ["weak"] * 15 + ["strong"] * 3 + ["weak"] * 2

# ADJACENT: 8 items, every disagreement is one band wide (moderate vs strong).
_ADJACENT_A = ["weak"] * 4 + ["moderate"] * 4
_ADJACENT_B = ["weak"] * 4 + ["strong"] * 4

# EXTREME: 8 items, every disagreement spans the whole scale (weak vs strong).
# Deliberately built so its percent agreement AND its unweighted kappa are identical to
# ADJACENT's. Only an ordinal statistic can tell these two rater pairs apart.
_EXTREME_A = ["weak"] * 4 + ["moderate"] * 4
_EXTREME_B = ["strong"] * 4 + ["moderate"] * 4


def _rows(rater_a: list[str], rater_b: list[str]) -> tuple[ItemRating, ...]:
    return tuple(
        ItemRating(item=f"i{n}", rater_a=a, rater_b=b)
        for n, (a, b) in enumerate(zip(rater_a, rater_b, strict=True))
    )


# ---------------------------------------------------------------------------------
# Why the ordinal statistic exists: percent agreement and weighted kappa disagree
# ---------------------------------------------------------------------------------


def test_should_report_worse_than_chance_when_percent_agreement_looks_healthy() -> None:
    # Given two raters who match on 15 of 20 items, both leaning heavily on "weak"
    # When percent agreement and quadratic kappa are both taken
    # Then percent agreement says three quarters and kappa says worse than nothing.
    # This is the whole reason the module exists: raters who share a habit agree often
    # without agreeing about anything.
    assert percent_agreement(_SKEW_A, _SKEW_B, scale=_SCALE) == pytest.approx(0.75)  # hand: 15/20
    # hand: marginals A = (0.9, 0, 0.1), B = (0.85, 0, 0.15)
    #       sum(d*observed) = 1*(3/20) + 1*(2/20)         = 0.25
    #       sum(d*expected) = 1*(0.9*0.15) + 1*(0.1*0.85) = 0.22
    #       kappa = 1 - 0.25/0.22 = -3/22
    assert quadratic_kappa(_SKEW_A, _SKEW_B, scale=_SCALE) == pytest.approx(-3 / 22)
    assert quadratic_kappa(_SKEW_A, _SKEW_B, scale=_SCALE) < 0.0


def test_should_separate_a_near_miss_from_a_total_miss_when_percent_agreement_cannot() -> None:
    # Given two rater pairs that agree on exactly half their items — one whose misses are
    # all one band wide, one whose misses span the entire scale
    assert percent_agreement(_ADJACENT_A, _ADJACENT_B, scale=_SCALE) == pytest.approx(0.5)
    assert percent_agreement(_EXTREME_A, _EXTREME_B, scale=_SCALE) == pytest.approx(0.5)
    # When quadratic kappa is taken
    # hand (adjacent): sum(d*observed) = 0.25*0.5                            = 0.125
    #                  sum(d*expected) = 1*0.25 + 0.25*0.25 + 0.25*0.25      = 0.375
    #                  kappa = 1 - 0.125/0.375 = 2/3
    assert quadratic_kappa(_ADJACENT_A, _ADJACENT_B, scale=_SCALE) == pytest.approx(2 / 3)
    # hand (extreme):  sum(d*observed) = 1*0.5                               = 0.5
    #                  sum(d*expected) = 0.25*0.25 + 1*0.25 + 0.25*0.25      = 0.375
    #                  kappa = 1 - 0.5/0.375 = -1/3
    assert quadratic_kappa(_EXTREME_A, _EXTREME_B, scale=_SCALE) == pytest.approx(-1 / 3)
    # Then one is good agreement and the other is worse than chance, while percent
    # agreement — and UNWEIGHTED kappa, which is (0.5 - 0.25) / (1 - 0.25) = 1/3 for
    # BOTH of them — reports the two rater pairs as identical.


def test_should_weight_a_one_band_miss_at_a_quarter_of_a_full_scale_miss() -> None:
    # Given the two rating sets above
    # When the per-item quadratic weights are averaged
    # Then an adjacent miss costs a quarter and a full-scale miss costs everything
    # hand (adjacent): (4*1.0 + 4*(1 - 0.25)) / 8 = 0.875
    assert weighted_agreement(_ADJACENT_A, _ADJACENT_B, scale=_SCALE) == pytest.approx(0.875)
    # hand (extreme):  (4*1.0 + 4*(1 - 1.0))  / 8 = 0.5
    assert weighted_agreement(_EXTREME_A, _EXTREME_B, scale=_SCALE) == pytest.approx(0.5)


# ---------------------------------------------------------------------------------
# The declared order IS the measurement
# ---------------------------------------------------------------------------------


def test_should_use_the_declared_band_order_and_not_an_alphabetical_one() -> None:
    # Given a scale whose declared order (weak < moderate < strong) is nothing like its
    # alphabetical order (moderate < strong < weak)
    assert sorted(_SCALE) == ["moderate", "strong", "weak"]
    # When the EXTREME set is scored against the declared order
    # Then kappa is -1/3, as hand-computed above.
    assert quadratic_kappa(_EXTREME_A, _EXTREME_B, scale=_SCALE) == pytest.approx(-1 / 3)
    # And had the order been inferred instead of declared, the SAME ratings would score
    # +2/3 — a good grader pair instead of a worse-than-chance one.
    # hand (alphabetical positions moderate=0, strong=1, weak=2):
    #       sum(d*observed) = 0.25*0.5                        = 0.125
    #       sum(d*expected) = 0.25*0.25 + 1*0.25 + 0.25*0.25  = 0.375
    #       kappa = 1 - 0.125/0.375 = 2/3
    assert quadratic_kappa(_EXTREME_A, _EXTREME_B, scale=tuple(sorted(_SCALE))) == pytest.approx(
        2 / 3
    )


def test_should_keep_an_unused_band_on_the_scale_when_measuring_distance() -> None:
    # Given a 3-band scale on which nobody used the middle band
    rater_a = ["weak", "weak", "strong", "strong"]
    rater_b = ["weak", "strong", "strong", "weak"]
    # When kappa is taken
    # Then "weak vs strong" is still a two-step miss, because the scale has three levels
    # whether or not the raters used all of them. Dropping the unused band would make it
    # a one-step miss on a two-level scale and change the answer.
    # hand: marginals A = (0.5, 0, 0.5), B = (0.5, 0, 0.5)
    #       sum(d*observed) = 1*0.25 + 1*0.25         = 0.5
    #       sum(d*expected) = 1*(0.5*0.5) + 1*(0.5*0.5) = 0.5
    #       kappa = 1 - 0.5/0.5 = 0.0
    assert quadratic_kappa(rater_a, rater_b, scale=_SCALE) == pytest.approx(0.0)


# ---------------------------------------------------------------------------------
# Kendall's tau-b — rank concordance, which is a different question
# ---------------------------------------------------------------------------------


def test_should_report_perfect_concordance_when_only_the_level_disagrees() -> None:
    # Given the ADJACENT pair: they agree on every ORDERING (weak below the other band)
    # and differ only on how high the other band sits
    # When tau-b is taken
    # hand: 16 cross-group pairs, all concordant; within-group pairs are ties on both
    #       sides. tau-b = (16 - 0) / sqrt((28-12)(28-12)) = 1.0
    assert kendall_tau_b(_ADJACENT_A, _ADJACENT_B, scale=_SCALE) == pytest.approx(1.0)
    # Then tau-b is perfect while kappa is only 2/3 — the two statistics answer different
    # questions, and a report that carried only one of them would be missing the other.
    assert quadratic_kappa(_ADJACENT_A, _ADJACENT_B, scale=_SCALE) == pytest.approx(2 / 3)


def test_should_report_perfect_discordance_when_the_order_is_inverted() -> None:
    # Given the EXTREME pair, whose orderings are exactly opposite
    # When tau-b is taken
    # hand: all 16 cross-group pairs discordant -> (0 - 16) / sqrt(16*16) = -1.0
    assert kendall_tau_b(_EXTREME_A, _EXTREME_B, scale=_SCALE) == pytest.approx(-1.0)


def test_should_correct_tau_for_ties_the_three_band_scale_forces() -> None:
    # Given the SKEW pair, where 18 of 20 ratings tie on one side and 17 on the other
    # When tau-b is taken
    # Then the tie correction is in the denominator — this is tau-B, not tau-A or tau-C.
    # hand: n0 = 20*19/2 = 190
    #       n1 (ties in A) = C(18,2) + C(2,2) = 153 + 1 = 154
    #       n2 (ties in B) = C(17,2) + C(3,2) = 136 + 3 = 139
    #       concordant 0, discordant 6
    #       tau-b = -6 / sqrt((190-154)(190-139)) = -6 / sqrt(36*51) = -1/sqrt(51)
    assert kendall_tau_b(_SKEW_A, _SKEW_B, scale=_SCALE) == pytest.approx(-1 / np.sqrt(51))


# ---------------------------------------------------------------------------------
# Degenerate rating sets: undefined, never dressed up as perfect
# ---------------------------------------------------------------------------------


def test_should_report_kappa_undefined_when_both_raters_never_varied() -> None:
    # Given two raters who put every item in the same single band
    rater_a = ["moderate"] * 6
    rater_b = ["moderate"] * 6
    # When the statistics are taken
    # Then percent agreement is a perfectly true 100%, and kappa is UNDEFINED rather
    # than 1.0: agreement by chance is also 100%, so the correction is 0/0. Reporting
    # 1.0 here would be the single most flattering lie this module could tell.
    assert percent_agreement(rater_a, rater_b, scale=_SCALE) == 1.0
    assert quadratic_kappa(rater_a, rater_b, scale=_SCALE) is None
    assert kendall_tau_b(rater_a, rater_b, scale=_SCALE) is None


def test_should_still_measure_kappa_when_only_one_rater_never_varied() -> None:
    # Given a rater who called everything "weak" against one who used the whole scale
    rater_a = ["weak"] * 4
    rater_b = ["weak", "weak", "moderate", "strong"]
    # When kappa is taken
    # Then it is exactly 0.0 — a rater with no variation agrees exactly as often as
    # chance predicts, no more. hand: expected == observed when one marginal is a point
    # mass, so 1 - (0.3125 / 0.3125) = 0.0
    assert quadratic_kappa(rater_a, rater_b, scale=_SCALE) == pytest.approx(0.0)
    # And tau-b is undefined: a constant column has no ranks to concord.
    assert kendall_tau_b(rater_a, rater_b, scale=_SCALE) is None


def test_should_report_one_when_the_two_raters_are_identical() -> None:
    # Given two raters who used the whole scale and agreed on every item
    ratings = ["weak", "moderate", "strong", "moderate"]
    # When every statistic is taken
    # Then all of them are perfect — the degenerate case above is about NO VARIATION,
    # not about agreement
    assert percent_agreement(ratings, ratings, scale=_SCALE) == 1.0
    assert weighted_agreement(ratings, ratings, scale=_SCALE) == 1.0
    assert quadratic_kappa(ratings, ratings, scale=_SCALE) == pytest.approx(1.0)
    assert kendall_tau_b(ratings, ratings, scale=_SCALE) == pytest.approx(1.0)


# ---------------------------------------------------------------------------------
# Refusals — every one of these would otherwise return a number nobody should believe
# ---------------------------------------------------------------------------------


def test_should_refuse_a_band_that_is_not_on_the_declared_scale() -> None:
    # Given a rating naming a band the scale does not declare
    # When any statistic is taken
    # Then it refuses. scikit-learn would silently DISCARD that item — the number comes
    # back looking fine, computed over fewer items than the caller handed in.
    with pytest.raises(InvalidAgreementRequest) as caught:
        quadratic_kappa(["weak", "excellent"], ["weak", "strong"], scale=_SCALE)
    assert caught.value.code == "assay.invalid_agreement_request"
    with pytest.raises(InvalidAgreementRequest):
        kendall_tau_b(["weak", "strong"], ["weak", "EXCELLENT"], scale=_SCALE)


def test_should_refuse_when_the_two_raters_graded_different_numbers_of_items() -> None:
    # Given two rating vectors of different length
    # When any statistic is taken
    # Then it refuses rather than truncating to the shorter one, which would silently
    # drop the tail and score a different item set than the caller asked about
    with pytest.raises(InvalidAgreementRequest):
        percent_agreement(["weak", "strong"], ["weak"], scale=_SCALE)


def test_should_refuse_an_empty_item_set() -> None:
    # Given no items at all
    # When any statistic is taken
    # Then it refuses rather than reporting agreement over nothing
    with pytest.raises(InvalidAgreementRequest):
        percent_agreement([], [], scale=_SCALE)
    with pytest.raises(InvalidAgreementRequest):
        agreement_report((), scale=_SCALE, settings=AssaySettings())


def test_should_refuse_a_scale_with_fewer_than_two_levels() -> None:
    # Given a scale that names one band, or none
    # When any statistic is taken
    # Then it refuses: with a single level every rating is identical by construction and
    # "agreement" measures nothing. It also makes the quadratic weight divide by L-1 = 0.
    for bad_scale in ((), ("only",)):
        with pytest.raises(InvalidAgreementRequest):
            percent_agreement(["only"], ["only"], scale=bad_scale)


def test_should_refuse_a_scale_that_names_the_same_band_twice() -> None:
    # Given a scale with a duplicated band
    # When any statistic is taken
    # Then it refuses: that band would sit at two positions at once, so the distance
    # between it and anything else is undecidable
    with pytest.raises(InvalidAgreementRequest):
        percent_agreement(["low"], ["low"], scale=("low", "high", "low"))


def test_should_refuse_the_same_item_graded_twice() -> None:
    # Given a report whose rows name the same item twice
    rows = (
        ItemRating(item="dupe", rater_a="weak", rater_b="weak"),
        ItemRating(item="dupe", rater_a="strong", rater_b="weak"),
    )
    # When the report is asked for
    # Then it refuses. A duplicate lets one disputed item vote twice and quietly reweights
    # the whole measurement toward whichever item was pasted in twice.
    with pytest.raises(InvalidAgreementRequest):
        agreement_report(rows, scale=_SCALE, settings=AssaySettings())


# ---------------------------------------------------------------------------------
# The aggregate report
# ---------------------------------------------------------------------------------


def test_should_report_every_statistic_alongside_the_counts() -> None:
    # Given the SKEW rating set as report rows
    # When the report is built
    report = agreement_report(_rows(_SKEW_A, _SKEW_B), scale=_SCALE, settings=AssaySettings())
    # Then it carries the scale it was measured under, the raw counts, and both statistics
    assert report.scale == _SCALE
    assert report.n_items == 20
    assert report.n_exact_matches == 15
    assert report.percent_agreement == pytest.approx(0.75)  # hand: 15/20
    assert report.weighted_agreement == pytest.approx(0.75)  # hand: (15*1 + 5*0) / 20
    assert report.quadratic_kappa == pytest.approx(-3 / 22)
    assert report.kendall_tau_b == pytest.approx(-1 / np.sqrt(51))
    assert report.kappa_undefined_reason is None
    assert report.tau_undefined_reason is None


def test_should_name_the_reason_when_a_statistic_is_undefined() -> None:
    # Given six items both raters put in the same single band
    rows = _rows(["moderate"] * 6, ["moderate"] * 6)
    # When the report is built
    report = agreement_report(rows, scale=_SCALE, settings=AssaySettings())
    # Then the undefined statistics are None AND the report says why, in a sentence a
    # reader can act on — a bare None reads as "not computed" rather than "cannot exist"
    assert report.quadratic_kappa is None
    assert report.kendall_tau_b is None
    assert report.kappa_undefined_reason is not None
    assert "chance" in report.kappa_undefined_reason
    assert report.tau_undefined_reason is not None
    assert "single band" in report.tau_undefined_reason


def test_should_abstain_on_the_interval_when_there_are_too_few_items() -> None:
    # Given fewer items than the sample floor
    settings = AssaySettings(min_samples=30)
    # When the report is built
    report = agreement_report(_rows(_SKEW_A, _SKEW_B), scale=_SCALE, settings=settings)
    # Then the weighted agreement is still reported, but its interval abstains — the same
    # honesty floor the classification and ranking faces use, not a third story.
    assert report.weighted_agreement == pytest.approx(0.75)
    assert isinstance(report.weighted_agreement_interval, Abstention)
    assert report.weighted_agreement_interval.n_samples == 20
    assert report.weighted_agreement_interval.min_samples == 30


def test_should_return_a_bootstrap_interval_when_above_the_floor() -> None:
    # Given enough doubly-graded items to support an interval
    settings = AssaySettings(min_samples=10, bootstrap_resamples=499)
    rows = _rows(_SKEW_A * 2, _SKEW_B * 2)
    # When the report is built
    report = agreement_report(rows, scale=_SCALE, settings=settings)
    # Then the interval brackets the point estimate, which is the weighted agreement
    interval = report.weighted_agreement_interval
    assert isinstance(interval, Interval)
    assert interval.low <= interval.point <= interval.high
    assert interval.point == pytest.approx(report.weighted_agreement)


def test_should_refuse_to_mutate_a_report() -> None:
    # Given a built report
    report = agreement_report(_rows(_SKEW_A, _SKEW_B), scale=_SCALE, settings=AssaySettings())
    # When a field is assigned
    # Then it refuses: the report is the evidence, and evidence does not get edited
    with pytest.raises(ValueError, match="frozen"):
        report.quadratic_kappa = 1.0  # type: ignore[misc]
