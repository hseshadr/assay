"""Ordinal agreement — did two graders mean the same thing, or just share a habit?

``metrics.py`` scores predictions against ground truth. This module scores two *raters*
against each other, when what they emit is a band on an ordered scale (weak / moderate /
strong) rather than a number. That shape has no ground truth to score against: nobody
knows the true band, only whether two independent graders landed in the same place.

**Why percent agreement is the wrong statistic here**, and the reason this module exists:

1. It is blind to *distance*. On a three-band scale, one grader saying "strong" while the
   other says "moderate" is a near miss; "strong" against "weak" is a total miss. Percent
   agreement scores both as simply "not a match".
2. It counts agreement that chance alone would produce. Two graders who both call 90% of
   everything "weak" will match about 80% of the time while agreeing about nothing.

One-line definitions, since none of these terms carry themselves:

- **quadratic-weighted Cohen's kappa** — agreement after subtracting the agreement two
  independent graders with these same habits would have produced, with each miss charged
  by the *square* of how many bands apart it was. 1.0 is perfect, 0.0 is exactly chance,
  and negative means the two graders did worse than if they had ignored each other.
- **Kendall's tau-b** — of every pair of items, how often the two graders put them in the
  same relative order. +1 perfectly concordant, -1 perfectly inverted. The ``b`` is the
  tie correction, which a three-band scale over many items needs badly.

They answer different questions and the report carries both: two graders who agree on
every *ordering* but sit one band apart on the level score tau-b 1.0 and kappa 2/3.

*The engines.* Kappa is ``sklearn.metrics.cohen_kappa_score(weights="quadratic")`` and
tau-b is ``scipy.stats.kendalltau(variant="b")`` — both already pinned dependencies, both
the reference implementation their field validates against, and neither needs a line of
correction at the boundary. Assay contributes what they do not: a declared band order
that cannot be guessed wrong, a refusal for every input whose answer would be undefined,
and an uncertainty interval on the same honesty floor the rest of the package uses.

*The trap this module is built around.* ``cohen_kappa_score`` derives the ordinal
distance between two bands from their **positions in its ``labels`` argument**. Leave
that argument off and it sorts the band names alphabetically, so "moderate < strong <
weak" — and the same ratings come back with a completely different, entirely plausible
number. Sorted-by-accident is not a scale. The caller declares the order, always.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy.stats import kendalltau
from sklearn.metrics import cohen_kappa_score

from assay.errors import InvalidAgreementRequest
from assay.models import ItemRating
from assay.settings import AssaySettings
from assay.uncertainty import Estimate, mean_interval

type Scale = Sequence[str]
"""The band names in order, weakest first. The order IS the measurement."""

_MIN_LEVELS = 2
"""Below two bands there is nothing to disagree about, and the quadratic weight's
``L - 1`` denominator is zero."""

_KAPPA_UNDEFINED = (
    "both raters put every item in the same single band, so agreement by chance is total "
    "and kappa's correction divides by zero"
)
_TAU_UNDEFINED = (
    "at least one rater used a single band for every item, so there is no rank variation "
    "for tau-b to concord"
)

__all__ = [
    "AgreementReport",
    "Scale",
    "agreement_report",
    "kendall_tau_b",
    "percent_agreement",
    "quadratic_kappa",
    "weighted_agreement",
]


class AgreementReport(BaseModel):
    """Two graders on one ordinal scale, and how much of their agreement is real.

    ``weighted_agreement_interval`` is a bootstrap confidence interval over the per-item
    quadratic agreement, or an ``Abstention`` when there are fewer items than the sample
    floor — the same uncertainty story the classification and ranking faces tell, not a
    third one. It is deliberately NOT an interval on kappa: kappa is not the mean of any
    per-item quantity, so no bootstrap of a mean can put an interval on it, and pairing
    it with one would be exactly the fake precision this package refuses to print.

    ``quadratic_kappa`` and ``kendall_tau_b`` are ``None`` when the ratings are too
    degenerate for the statistic to exist, and the matching ``*_undefined_reason`` says
    which degeneracy it was. A bare ``None`` reads as "not computed"; the reason says
    "cannot exist", which is a different fact about the data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scale: tuple[str, ...]
    n_items: int
    n_exact_matches: int
    percent_agreement: float
    weighted_agreement: float
    quadratic_kappa: float | None
    kappa_undefined_reason: str | None
    kendall_tau_b: float | None
    tau_undefined_reason: str | None
    weighted_agreement_interval: Estimate


def _require_scale(scale: Scale) -> None:
    if len(scale) < _MIN_LEVELS:
        raise InvalidAgreementRequest(
            f"an ordinal scale needs at least {_MIN_LEVELS} bands, got {len(scale)}"
        )
    if len(set(scale)) != len(scale):
        raise InvalidAgreementRequest("the scale names the same band twice")


def _require_paired(rater_a: Sequence[str], rater_b: Sequence[str]) -> None:
    if len(rater_a) != len(rater_b):
        raise InvalidAgreementRequest(
            f"the raters graded different numbers of items: {len(rater_a)} vs {len(rater_b)}"
        )
    if not rater_a:
        raise InvalidAgreementRequest("no items were graded; there is nothing to agree about")


def _ordinals(ratings: Sequence[str], positions: Mapping[str, int]) -> list[int]:
    """Band names as positions on the declared scale, refusing any band not on it.

    The refusal is load-bearing, not defensive. ``cohen_kappa_score`` silently DROPS
    every row whose label is outside its ``labels`` argument, so an unknown band would
    return a perfectly healthy number computed over fewer items than were handed in."""
    unknown = sorted(set(ratings) - set(positions))
    if unknown:
        raise InvalidAgreementRequest(f"bands that are not on the declared scale: {unknown}")
    return [positions[band] for band in ratings]


def _validate(
    rater_a: Sequence[str], rater_b: Sequence[str], scale: Scale
) -> tuple[list[int], list[int]]:
    """Check everything, then return both raters as positions on the declared scale."""
    _require_scale(scale)
    _require_paired(rater_a, rater_b)
    positions = {band: index for index, band in enumerate(scale)}
    return _ordinals(rater_a, positions), _ordinals(rater_b, positions)


def _per_item_weights(rater_a: Sequence[int], rater_b: Sequence[int], levels: int) -> list[float]:
    """Cohen's quadratic weight per item: ``1 - ((i - j) / (L - 1)) ** 2``.

    1.0 for an exact match, falling with the SQUARE of the distance between bands — on a
    three-band scale an adjacent miss keeps 0.75 and an opposite-ends miss keeps 0.0."""
    span = levels - 1
    return [1.0 - ((a - b) / span) ** 2 for a, b in zip(rater_a, rater_b, strict=True)]


def percent_agreement(rater_a: Sequence[str], rater_b: Sequence[str], *, scale: Scale) -> float:
    """The fraction of items both raters put in exactly the same band.

    Carried because it is the number people reach for — and because the report exists to
    show, side by side, why it is not enough."""
    ordinals_a, ordinals_b = _validate(rater_a, rater_b, scale)
    matches = sum(a == b for a, b in zip(ordinals_a, ordinals_b, strict=True))
    return matches / len(ordinals_a)


def weighted_agreement(rater_a: Sequence[str], rater_b: Sequence[str], *, scale: Scale) -> float:
    """Mean per-item quadratic agreement: like percent agreement, but a near miss counts.

    Still uncorrected for chance — that correction is what kappa adds on top of it."""
    ordinals_a, ordinals_b = _validate(rater_a, rater_b, scale)
    return float(np.mean(_per_item_weights(ordinals_a, ordinals_b, len(scale))))


def quadratic_kappa(
    rater_a: Sequence[str], rater_b: Sequence[str], *, scale: Scale
) -> float | None:
    """Quadratic-weighted Cohen's kappa — ``sklearn.metrics.cohen_kappa_score``.

    ``labels=list(scale)`` is the whole ordinal contract: sklearn reads the distance
    between two bands off their positions in that list. Omit it and it sorts the band
    names, which for weak/moderate/strong is a different scale and a different answer.
    Passing the full declared scale also keeps a band nobody used at its own position,
    so "weak vs strong" stays a two-step miss on a three-band scale.

    ``None`` when both raters used one and the same band throughout: chance agreement is
    then total, kappa's denominator is zero, and there is no honest number to return."""
    _validate(rater_a, rater_b, scale)
    if len(set(rater_a) | set(rater_b)) < _MIN_LEVELS:
        return None
    return float(cohen_kappa_score(rater_a, rater_b, labels=list(scale), weights="quadratic"))


def kendall_tau_b(rater_a: Sequence[str], rater_b: Sequence[str], *, scale: Scale) -> float | None:
    """Kendall's tau-b over the two raters' band positions — ``scipy.stats.kendalltau``.

    ``variant="b"`` is the tie-corrected form, and ties are the normal case here: a
    three-band scale over fifty items ties constantly. tau-a would divide by every pair
    including the tied ones and report near-zero concordance for graders who track each
    other exactly.

    ``None`` when either rater used a single band throughout — a constant column has no
    ranks to be concordant with."""
    ordinals_a, ordinals_b = _validate(rater_a, rater_b, scale)
    if min(len(set(ordinals_a)), len(set(ordinals_b))) < _MIN_LEVELS:
        return None
    return float(kendalltau(ordinals_a, ordinals_b, variant="b").statistic)


def _require_distinct_items(ratings: Sequence[ItemRating]) -> None:
    items = [row.item for row in ratings]
    if len(set(items)) != len(items):
        raise InvalidAgreementRequest("the same item is graded twice")


def _interval(per_item: Sequence[float], settings: AssaySettings) -> Estimate:
    return mean_interval(
        per_item,
        min_samples=settings.min_samples,
        n_resamples=settings.bootstrap_resamples,
        confidence_level=settings.confidence_level,
        seed=settings.bootstrap_seed,
    )


def _report(
    rater_a: Sequence[str],
    rater_b: Sequence[str],
    scale: Scale,
    per_item: Sequence[float],
    settings: AssaySettings,
) -> AgreementReport:
    kappa = quadratic_kappa(rater_a, rater_b, scale=scale)
    tau = kendall_tau_b(rater_a, rater_b, scale=scale)
    return AgreementReport(
        scale=tuple(scale),
        n_items=len(per_item),
        n_exact_matches=sum(a == b for a, b in zip(rater_a, rater_b, strict=True)),
        percent_agreement=percent_agreement(rater_a, rater_b, scale=scale),
        weighted_agreement=float(np.mean(per_item)),
        quadratic_kappa=kappa,
        kappa_undefined_reason=None if kappa is not None else _KAPPA_UNDEFINED,
        kendall_tau_b=tau,
        tau_undefined_reason=None if tau is not None else _TAU_UNDEFINED,
        weighted_agreement_interval=_interval(per_item, settings),
    )


def agreement_report(
    ratings: Sequence[ItemRating], *, scale: Scale, settings: AssaySettings
) -> AgreementReport:
    """Score one set of doubly-graded items: the counts, both statistics, and an interval.

    ``ratings`` is item-keyed rather than two loose parallel lists, because the item id is
    what makes "the same item graded twice" detectable — a duplicate would let one
    disputed item vote twice and quietly reweight the whole measurement."""
    _require_distinct_items(ratings)
    rater_a = [row.rater_a for row in ratings]
    rater_b = [row.rater_b for row in ratings]
    ordinals_a, ordinals_b = _validate(rater_a, rater_b, scale)
    per_item = _per_item_weights(ordinals_a, ordinals_b, len(scale))
    return _report(rater_a, rater_b, scale, per_item, settings)
