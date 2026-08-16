"""Typed request models at the input boundary. Frozen and ``extra="forbid"`` so a
malformed or ambiguous request is rejected before any computation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ScoreRequest(BaseModel):
    """A classification scoring request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    metric_version: str
    y_true: tuple[int, ...]
    y_score: tuple[float, ...]
    threshold: float = 0.5


class SubScoreInput(BaseModel):
    """One sub-score with its native scale and interval, for a composite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: float
    low: float
    high: float
    scale_min: float
    scale_max: float
    weight: float


class CompositeRequest(BaseModel):
    """A weighted multi-scale composite request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = "weighted_composite"
    metric_version: str
    subscores: tuple[SubScoreInput, ...]


class RelevanceJudgment(BaseModel):
    """How relevant one document is to one query.

    ``gain`` 0 means judged and not relevant; any positive gain means relevant, and a
    larger gain means more relevant. Binary judgments are the special case where every
    listed document has gain 1.0."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str
    gain: float = 1.0


class RankedQuery(BaseModel):
    """One query's scoring inputs: the returned order and relevance judgments.

    ``ranked`` is a *position* list — first element is the top hit — not scores. The two
    are deliberately separate: a ranking is judged against the whole judgment set,
    including relevant documents the system never returned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    judgments: tuple[RelevanceJudgment, ...]
    ranked: tuple[str, ...]


class ItemRating(BaseModel):
    """One item, and the band each of two raters put it in.

    Item-keyed rather than two loose parallel lists: the id is what makes "the same item
    graded twice" detectable, and a silent duplicate lets one disputed item vote twice."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item: str
    rater_a: str
    rater_b: str


class AgreementRequest(BaseModel):
    """An inter-rater agreement request over one set of doubly-graded items.

    ``scale`` is ORDERED, weakest band first. The declared order is part of the scoring
    method and result explanation because changing it changes the measurement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = "agreement"
    metric_version: str
    scale: tuple[str, ...]
    ratings: tuple[ItemRating, ...]


class RankingRequest(BaseModel):
    """A ranked-retrieval scoring request over a whole query set.

    ``k`` left as ``None`` means "use ``AssaySettings.ranking_k``"; whichever value ends
    up applying is method provenance, so a reported precision@k always explains which k
    it used."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = "ranking"
    metric_version: str
    queries: tuple[RankedQuery, ...]
    k: int | None = None
