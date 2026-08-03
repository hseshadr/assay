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
    """One query's evidence: what the system returned, in order, and what was judged.

    ``ranked`` is a *position* list — first element is the top hit — not scores. The two
    are deliberately separate: a ranking is judged against the whole judgment set,
    including relevant documents the system never returned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    judgments: tuple[RelevanceJudgment, ...]
    ranked: tuple[str, ...]


class RankingRequest(BaseModel):
    """A ranked-retrieval scoring request over a whole query set.

    ``k`` left as ``None`` means "use ``AssaySettings.ranking_k``"; whichever value ends
    up applying is recorded in the receipt, so a reported precision@k always says which
    k it was."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = "ranking"
    metric_version: str
    queries: tuple[RankedQuery, ...]
    k: int | None = None
