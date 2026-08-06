"""Mutation harness: break a named guard on purpose, and watch the suite go red.

**Why this file exists.** A green test suite is not evidence that a guard guards. A test
that asserts whatever the code happens to return goes green whether the property holds
or not, and the only way to tell those two apart is to break the property and watch the
test fail. This harness does that mechanically, once per claim, so the evidence is
re-runnable by anyone rather than narrated in a commit message.

**How it reads its own results.** The verdict is the pytest **exit code**, never its
output. A harness that greps stdout for "failed" reports green when the runner crashes,
because a crash prints no failures either. pytest's exit codes are unambiguous: ``0``
every test passed, ``1`` a test failed, ``2``/``3``/``4`` interrupted / internal /
usage error, ``5`` nothing was collected. Only ``1`` counts as a guard firing; every
other code is its own named harness failure.

Each mutation runs its named guard tests twice and then restores the file:

1. **before** — unmutated, must exit ``0``. Proves the guard exists, collects and passes.
2. **after** — mutated, must exit ``1``. Proves the guard fails when the property breaks.
3. **restore** — the original bytes are written back and compared, in a ``finally``.

The mutation is read back off disk before the second run, so an edit that silently
failed to apply can never be reported as a guard that held.

**It breaks TypeScript too.** Half the guards below live in ``ts/src``, because half
the claims do: ``@edgeproc/avow`` ships the same metrics as the Python face and is
pinned to it by shared golden vectors. A guard that only Python can break is a guard
that only defends Python. Vitest's verdict is read from the JSON reporter's
pass/fail counts rather than its exit code, and that is not a stylistic choice —
``vitest run -t 'no-such-test'`` **exits 0**, reporting every test in the file as
"total" while running none of them. An exit-code reading of that is a green baseline
for a guard that does not exist. ``numPassedTests`` is the only field that says
something ran. If the reporter writes no file at all — which is what a misspelled
reporter name does — that is a harness error, never a verdict.

Run it::

    uv run poe mutants

It edits tracked files in place, so it refuses to start unless every file it will touch
is clean in git. The TypeScript half needs ``ts/node_modules`` installed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TS = _ROOT / "ts"

# pytest's documented exit codes. The verdict is read from these and from nothing else,
# and the vitest runner below maps its own JSON counts onto the same three numbers so
# one report can hold both languages.
_ALL_PASSED = 0
_TESTS_FAILED = 1
_NOTHING_COLLECTED = 5

_PYTEST = "pytest"
_VITEST = "vitest"

# A one-item file has nothing to drop, so the vector-count mutation could not apply.
_MIN_VECTORS_TO_DROP_ONE = 2

_RANKING = "src/assay/ranking.py"
_AGREEMENT = "src/assay/agreement.py"
_METRICS = "src/assay/metrics.py"
_ENVELOPE = "src/avow/envelope.py"
_LEDGER = "src/avow/ledger.py"
_SETTINGS = "src/assay/settings.py"
_VECTORS = "testdata/vectors/canonical.json"
_METRIC_VECTORS = "testdata/vectors/metrics.json"
_PNPM_WORKSPACE = "ts/pnpm-workspace.yaml"
_TS_RANKING = "ts/src/ranking.ts"
_TS_METRICS = "ts/src/metrics.ts"


class MutationNotAppliedError(RuntimeError):
    """The edit did not reach the file, so its result would prove nothing."""


class HarnessError(RuntimeError):
    """The runner itself failed, so neither run is evidence of anything."""


@dataclass(frozen=True)
class Mutation:
    """One break, the claim it breaks, and the tests that must notice.

    ``guard`` entries are pytest node ids by default. When ``runner`` is ``vitest``
    they are ``<file>::<test name>`` instead — the same shape, resolved against
    vitest's file filter and ``--testNamePattern``."""

    name: str
    claim: str
    target: str
    guard: tuple[str, ...]
    edit: Callable[[str], str]
    runner: str = field(default=_PYTEST)


def _replace_once(old: str, new: str) -> Callable[[str], str]:
    """Replace an anchor that must occur exactly once.

    An anchor that has moved or been reworded is a hard stop, not a skipped mutation:
    silently matching zero times is exactly how a harness reports twelve green runs it
    never actually performed."""

    def edit(text: str) -> str:
        found = text.count(old)
        if found != 1:
            raise MutationNotAppliedError(
                f"anchor occurs {found}x, expected exactly 1: {old.strip()!r}"
            )
        return text.replace(old, new)

    return edit


def _drop_last_vector(text: str) -> str:
    """Delete one golden vector, so a count the README states out loud stops being true."""
    vectors = json.loads(text)
    if len(vectors) < _MIN_VECTORS_TO_DROP_ONE:
        raise MutationNotAppliedError("fewer than two vectors; nothing to drop")
    return json.dumps(vectors[:-1], indent=2) + "\n"


def _drop_last_metric_vector(text: str) -> str:
    """Delete one shared metric case, so the count the README promises stops being true."""
    vectors = json.loads(text)
    if len(vectors["ranking"]) < _MIN_VECTORS_TO_DROP_ONE:
        raise MutationNotAppliedError("fewer than two ranking cases; nothing to drop")
    vectors["ranking"] = vectors["ranking"][:-1]
    return json.dumps(vectors, indent=2) + "\n"


def _delete_throw(statement: str) -> Callable[[str], str]:
    """Remove a refusal, leaving its ``if`` block empty but syntactically valid.

    The TypeScript counterpart of replacing a Python ``raise`` with ``pass``."""
    return _replace_once(statement, "      // mutated: this refusal was deleted")


MUTATIONS: tuple[Mutation, ...] = (
    # ----------------------------------------------------------------------------------
    # The ranking metrics are trec_eval's arithmetic, reached through ir_measures.
    # Every mutation below breaks the WIRING to that engine, not assay's own maths.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="ranking-order-reaches-trec-eval",
        claim="the ranked ORDER is what trec_eval scores, not merely the retrieved set",
        target=_RANKING,
        guard=(
            "tests/test_ranking.py::test_should_rank_a_better_order_above_a_worse_one_when_the_set_is_identical",
            "tests/test_ranking.py::test_should_score_clearly_below_one_when_the_ranking_is_exactly_reversed",
            "tests/test_ranking.py::test_should_report_the_reciprocal_of_the_first_hit_position",
        ),
        edit=_replace_once(
            "    return {_QUERY: {doc: float(len(ranked) - i) for i, doc in enumerate(ranked)}}",
            "    return {_QUERY: dict.fromkeys(ranked, 1.0)}",
        ),
    ),
    Mutation(
        name="ranking-k-reaches-trec-eval",
        claim="the cut-off k is handed to the engine, not ignored",
        target=_RANKING,
        guard=(
            "tests/test_ranking.py::test_should_count_hits_over_k_when_measuring_precision",
            "tests/test_ranking.py::test_should_charge_for_the_empty_positions_when_k_exceeds_the_list",
        ),
        edit=_replace_once(
            "    return _score(relevant, ranked, P @ k)",
            "    return _score(relevant, ranked, P @ 1)",
        ),
    ),
    Mutation(
        name="ranking-recall-is-not-precision",
        claim="recall@k divides by the relevant set, never by k",
        target=_RANKING,
        guard=(
            "tests/test_ranking.py::test_should_divide_by_the_relevant_set_not_k_when_measuring_recall",
            "tests/test_ranking.py::test_should_separate_precision_from_recall_when_relevant_set_is_larger_than_k",
        ),
        edit=_replace_once(
            "    return _score(relevant, ranked, R @ k)",
            "    return _score(relevant, ranked, P @ k)",
        ),
    ),
    Mutation(
        name="ranking-graded-gains-reach-trec-eval",
        claim="graded relevance is graded — a 3 outranks a 1, it is not collapsed to binary",
        target=_RANKING,
        guard=(
            "tests/test_ranking.py::test_should_reward_putting_the_heavier_grade_first_when_relevance_is_graded",
            "tests/test_ranking.py::test_should_score_clearly_below_one_when_the_ranking_is_exactly_reversed",
        ),
        edit=_replace_once(
            "    return {_QUERY: {doc: int(gain) for doc, gain in relevant.items()}}",
            "    return {_QUERY: dict.fromkeys(relevant, 1)}",
        ),
    ),
    Mutation(
        name="ranking-average-precision-is-trec-eval-map",
        claim="average_precision is trec_eval's AP, not some other rank measure",
        target=_RANKING,
        guard=(
            "tests/test_ranking.py::test_should_average_precision_over_every_hit_position",
            "tests/test_ranking.py::test_should_divide_average_precision_by_the_full_relevant_set",
        ),
        edit=_replace_once(
            "    return _score(relevant, ranked, AP)",
            "    return _score(relevant, ranked, RR)",
        ),
    ),
    Mutation(
        name="ranking-f1-is-the-harmonic-mean",
        claim="F1@k is the harmonic mean of precision and recall, not their average",
        target=_RANKING,
        guard=("tests/test_ranking.py::test_should_take_the_harmonic_mean_when_measuring_f1",),
        edit=_replace_once(
            "    return 2 * precision * recall / (precision + recall)",
            "    return (precision + recall) / 2",
        ),
    ),
    # ----------------------------------------------------------------------------------
    # The refusals. Every one of these would otherwise return a number nobody should
    # believe, and an untested refusal branch is where this portfolio's holes have been.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="ranking-refuses-an-empty-relevant-set",
        claim="a query with nothing judged relevant is refused, not scored 0.0",
        target=_RANKING,
        guard=("tests/test_ranking.py::test_should_refuse_when_no_document_is_judged_relevant",),
        edit=_replace_once(
            '        raise EmptyRelevantSet("no document is judged relevant for this query")',
            "        pass",
        ),
    ),
    Mutation(
        name="ranking-refuses-a-fractional-gain",
        claim="a relevance grade of 2.5 is refused, never silently rounded",
        target=_RANKING,
        guard=("tests/test_ranking.py::test_should_refuse_a_fractional_relevance_gain",),
        edit=_replace_once(
            "            raise InvalidRankingRequest("
            'f"relevance gain for {doc!r} is not whole: {gain}")',
            "            pass",
        ),
    ),
    Mutation(
        name="ranking-refuses-a-duplicate-document",
        claim="a ranked list holding one document twice is refused, not de-duplicated",
        target=_RANKING,
        guard=(
            "tests/test_ranking.py::test_should_refuse_a_ranked_list_holding_the_same_document_twice",
        ),
        edit=_replace_once(
            '        raise InvalidRankingRequest("ranked list holds the same document id twice")',
            "        pass",
        ),
    ),
    # ----------------------------------------------------------------------------------
    # The agreement face. The statistics are sklearn's and scipy's; every mutation below
    # breaks the ORDINAL CONTRACT around them — which band order was used, whether the
    # distance between bands counts, and whether a degenerate input is allowed to pass
    # itself off as a number.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="agreement-declared-band-order-reaches-kappa",
        claim="the CALLER's band order sets the ordinal distances, not an alphabetical guess",
        target=_AGREEMENT,
        guard=(
            "tests/test_agreement.py::test_should_use_the_declared_band_order_and_not_an_alphabetical_one",
            "tests/test_agreement.py::test_should_separate_a_near_miss_from_a_total_miss_when_percent_agreement_cannot",
        ),
        # Dropping `labels` is the single most plausible edit here, and sklearn does not
        # complain: it sorts the band names instead, so weak/moderate/strong silently
        # becomes moderate < strong < weak and the SAME ratings score +2/3 instead of -1/3.
        edit=_replace_once(
            "    return float(cohen_kappa_score(rater_a, rater_b, "
            'labels=list(scale), weights="quadratic"))',
            '    return float(cohen_kappa_score(rater_a, rater_b, weights="quadratic"))',
        ),
    ),
    Mutation(
        name="agreement-kappa-is-quadratically-weighted",
        claim="a near miss costs less than a total miss — the scale is ordinal, not nominal",
        target=_AGREEMENT,
        guard=(
            "tests/test_agreement.py::test_should_separate_a_near_miss_from_a_total_miss_when_percent_agreement_cannot",
            "tests/test_agreement.py::test_should_report_worse_than_chance_when_percent_agreement_looks_healthy",
        ),
        # Unweighted kappa scores the two rater pairs in that first test IDENTICALLY
        # (1/3 each), which is precisely the blindness the weighting exists to remove.
        edit=_replace_once(
            'labels=list(scale), weights="quadratic"))',
            "labels=list(scale)))",
        ),
    ),
    Mutation(
        name="agreement-tau-b-corrects-for-ties",
        claim="tau-b's tie correction is applied, so a 3-band scale is not scored as ranks",
        target=_AGREEMENT,
        guard=(
            "tests/test_agreement.py::test_should_correct_tau_for_ties_the_three_band_scale_forces",
        ),
        edit=_replace_once(
            'kendalltau(ordinals_a, ordinals_b, variant="b")',
            'kendalltau(ordinals_a, ordinals_b, variant="c")',
        ),
    ),
    Mutation(
        name="agreement-refuses-a-band-off-the-declared-scale",
        claim="a band the scale does not declare is refused, never silently discarded",
        target=_AGREEMENT,
        guard=(
            "tests/test_agreement.py::test_should_refuse_a_band_that_is_not_on_the_declared_scale",
        ),
        edit=_replace_once(
            "        raise InvalidAgreementRequest("
            'f"bands that are not on the declared scale: {unknown}")',
            "        pass",
        ),
    ),
    Mutation(
        name="agreement-refuses-an-item-graded-twice",
        claim="the same item graded twice is refused, so no one item can vote twice",
        target=_AGREEMENT,
        guard=("tests/test_agreement.py::test_should_refuse_the_same_item_graded_twice",),
        edit=_replace_once(
            '        raise InvalidAgreementRequest("the same item is graded twice")',
            "        pass",
        ),
    ),
    Mutation(
        name="agreement-kappa-is-undefined-not-perfect-when-nobody-varied",
        claim="two raters who used one band throughout score UNDEFINED, never 1.0",
        target=_AGREEMENT,
        guard=(
            "tests/test_agreement.py::test_should_report_kappa_undefined_when_both_raters_never_varied",
            "tests/test_agreement.py::test_should_name_the_reason_when_a_statistic_is_undefined",
        ),
        # 1.0 is the flattering answer and the one a careless fix would reach for: they
        # did, after all, agree on every single item.
        edit=_replace_once(
            "    if len(set(rater_a) | set(rater_b)) < _MIN_LEVELS:\n        return None",
            "    if len(set(rater_a) | set(rater_b)) < _MIN_LEVELS:\n        return 1.0",
        ),
    ),
    # ----------------------------------------------------------------------------------
    # The confusion counts. A rate hides which way a system fails; these are the four
    # numbers that say, and two of them are trivially swappable without any total moving.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="metrics-confusion-cells-are-read-in-the-right-order",
        claim="a miss is not read back as a false alarm",
        target=_METRICS,
        guard=("tests/test_metrics.py::test_should_count_each_confusion_cell_by_hand",),
        # sklearn ravels the matrix as tn, fp, fn, tp. Swapping the middle pair keeps
        # every total identical and inverts what the system is failing at.
        edit=_replace_once(
            "    true_negatives, false_positives, false_negatives, "
            "true_positives = confusion_matrix(",
            "    true_negatives, false_negatives, false_positives, "
            "true_positives = confusion_matrix(",
        ),
    ),
    Mutation(
        name="metrics-false-negative-rate-counts-misses",
        claim="the FNR divides misses by real positives — it is not the false-ALARM rate",
        target=_METRICS,
        guard=(
            "tests/test_metrics.py::test_should_report_the_miss_rate_as_the_false_negative_rate",
            "tests/test_metrics.py::test_should_make_the_false_negative_rate_the_exact_complement_of_recall",
        ),
        edit=_replace_once(
            "    return counts.false_negatives / (counts.false_negatives + counts.true_positives)",
            "    return counts.false_positives / (counts.false_positives + counts.true_negatives)",
        ),
    ),
    Mutation(
        name="metrics-refuses-a-label-outside-zero-and-one",
        claim="a label outside {0, 1} is refused, never dropped from the counts",
        target=_METRICS,
        guard=("tests/test_metrics.py::test_should_refuse_a_label_outside_zero_and_one",),
        edit=_replace_once(
            '        raise InvalidScoreRequest(f"labels must be 0 or 1; got {outside}")',
            "        pass",
        ),
    ),
    # ----------------------------------------------------------------------------------
    # The envelope: what a receipt actually proves.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="envelope-recomputes-the-payload-hash",
        claim="verification re-derives the payload hash instead of believing the field",
        target=_ENVELOPE,
        guard=(
            "tests/test_receipt.py::test_should_raise_payload_hash_mismatch_when_hash_is_tampered",
        ),
        edit=_replace_once(
            '        raise PayloadHashMismatch("payload hash does not match payload content")',
            "        pass",
        ),
    ),
    Mutation(
        name="envelope-pins-the-signer",
        claim="a receipt carrying a key the caller did not pin is rejected before any maths",
        target=_ENVELOPE,
        guard=(
            "tests/test_verify.py::test_should_code_a_pinned_key_mismatch_as_a_signer_mismatch",
        ),
        edit=_replace_once(
            '        raise SignerMismatch("receipt public key is not the expected signer")',
            "        pass",
        ),
    ),
    # ----------------------------------------------------------------------------------
    # The ledger: append-only means chained, counted and signed — three separate checks.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="ledger-chains-each-entry-to-the-one-before",
        claim="the chain is walked link by link, not inferred from the last line",
        target=_LEDGER,
        # NOT the splice test, which this harness found survives with the link check
        # deleted: a spliced entry also breaks the count, so the head pin catches it
        # first. Only a rewritten interior prev_hash isolates the chain walk.
        guard=("tests/test_ledger.py::test_should_reject_a_ledger_whose_chain_link_was_rewritten",),
        edit=_replace_once(
            "        raise LedgerIntegrityError("
            'f"ledger entry {position} does not chain to the entry before it")',
            "        pass",
        ),
    ),
    Mutation(
        name="ledger-requires-the-pinned-head",
        claim="a self-consistent but truncated ledger is refused against the pinned head",
        target=_LEDGER,
        guard=("tests/test_ledger.py::test_should_reject_a_ledger_truncated_at_the_end",),
        edit=_replace_once(
            "        raise LedgerIntegrityError(\n"
            '            f"ledger ends at {head.count} entries / {head.head_hash}, "\n'
            '            f"but the pinned head is {expected_head.count} entries / '
            '{expected_head.head_hash}"\n'
            "        )",
            "        pass",
        ),
    ),
    Mutation(
        name="ledger-verifies-every-entry-signature",
        claim="a re-hashed forgery cannot launder itself past the pinned key",
        target=_LEDGER,
        guard=(
            "tests/test_ledger.py::test_should_reject_a_rehashed_tampered_entry_without_the_signing_key",
        ),
        edit=_replace_once(
            '        raise LedgerIntegrityError(f"tampered ledger entry: '
            '{receipt.payload_hash}") from exc',
            "        pass",
        ),
    ),
    # ----------------------------------------------------------------------------------
    # The literals the docs promise. A constant asserted only against itself is
    # unguarded: `assert settings.min_samples == settings.min_samples` holds at any value.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="documented-sample-floor-is-30",
        claim="the README's honesty floor of 30 samples is the shipped default",
        target=_SETTINGS,
        guard=("tests/test_settings.py::test_should_use_documented_defaults_when_no_env",),
        edit=_replace_once("    min_samples: int = 30", "    min_samples: int = 3"),
    ),
    Mutation(
        name="documented-confidence-level-is-95pc",
        claim="the README's '95% interval' is a 95% interval",
        target=_SETTINGS,
        guard=("tests/test_settings.py::test_should_use_documented_defaults_when_no_env",),
        edit=_replace_once(
            "    confidence_level: float = 0.95", "    confidence_level: float = 0.5"
        ),
    ),
    Mutation(
        name="documented-ranking-cutoff-is-10",
        claim="the documented first-page depth of 10 is the shipped default k",
        target=_SETTINGS,
        guard=(
            "tests/test_documented_constants.py::test_the_default_ranking_cutoff_the_docs_promise",
        ),
        edit=_replace_once("    ranking_k: int = 10", "    ranking_k: int = 4"),
    ),
    Mutation(
        name="documented-golden-vector-count-is-12",
        claim="the README's 9 canonicalization vectors + 3 receipts are all still shipped",
        target=_VECTORS,
        guard=(
            "tests/test_documented_constants.py::test_the_golden_vector_counts_the_readme_promises",
        ),
        edit=_drop_last_vector,
    ),
    # ----------------------------------------------------------------------------------
    # Not a claim about assay's maths — a claim about what assay will install. The
    # quarantine below is the guard that turned PR #21 red by refusing a transitive
    # dependency published hours earlier; lowering it is the one-line edit that would
    # retire it, so the suite has to notice that edit.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="npm-release-quarantine-is-24h",
        claim="a package published minutes ago cannot enter the TypeScript lockfile",
        target=_PNPM_WORKSPACE,
        guard=(
            "tests/test_supply_chain_policy.py::test_new_npm_releases_are_quarantined_for_a_day",
        ),
        edit=_replace_once("minimumReleaseAge: 1440", "minimumReleaseAge: 0"),
    ),
    # ----------------------------------------------------------------------------------
    # `@edgeproc/avow`'s metrics face. These run under VITEST, not pytest. The claims
    # are the same claims the Python block above makes, because the two faces are
    # pinned to one another — so the guards have to be able to fail in both languages.
    # The verdict comes from vitest's JSON pass/fail counts; see the module docstring
    # for why its exit code cannot be trusted for this.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="ts-ranking-precision-divides-by-k",
        claim="precision@k divides by k, so unfilled positions are charged for",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::charges for the empty positions when k exceeds the list",),
        edit=_replace_once(
            "  return hitsInTopK(relevant, ranked, k) / k;",
            "  return hitsInTopK(relevant, ranked, k) / ranked.length;",
        ),
    ),
    Mutation(
        name="ts-ranking-recall-is-not-precision",
        claim="recall@k divides by the relevant set, never by k",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::divides by the relevant set, never by k",),
        edit=_replace_once(
            "  return hitsInTopK(relevant, ranked, k) / relevantCount(relevant);",
            "  return hitsInTopK(relevant, ranked, k) / k;",
        ),
    ),
    Mutation(
        name="ts-ranking-scores-only-the-top-k-slice",
        claim="the ranked ORDER is what is scored, not merely the retrieved set",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=(
            "src/ranking.test.ts::counts hits over k",
            "src/ranking.test.ts::scores only the top-k slice, so order changes the answer",
        ),
        edit=_replace_once(
            "  return ranked.slice(0, k).filter((doc) => isRelevant(relevant, doc)).length;",
            "  return ranked.filter((doc) => isRelevant(relevant, doc)).length;",
        ),
    ),
    Mutation(
        name="ts-ranking-f1-is-the-harmonic-mean",
        claim="F1@k is the harmonic mean of precision and recall, not their average",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::takes the harmonic mean, not the average",),
        edit=_replace_once(
            "  return (2 * precision * recall) / (precision + recall);",
            "  return (precision + recall) / 2;",
        ),
    ),
    Mutation(
        name="ts-ranking-rr-is-the-first-hit",
        claim="reciprocal rank uses the FIRST relevant hit, not any later one",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::uses the first hit and not the last when there are several",),
        edit=_replace_once(
            "  const position = ranked.findIndex((doc) => isRelevant(relevant, doc));",
            "  const position = ranked.findLastIndex((doc) => isRelevant(relevant, doc));",
        ),
    ),
    Mutation(
        name="ts-ranking-a-zero-gain-is-not-relevant",
        claim="a judged gain of 0 is judged NOT relevant, it is not merely a low grade",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::treats a judged gain of zero as NOT relevant",),
        edit=_replace_once(
            "  return Object.hasOwn(relevant, doc) && (relevant[doc] as number) > 0;",
            "  return Object.hasOwn(relevant, doc) && (relevant[doc] as number) >= 0;",
        ),
    ),
    Mutation(
        name="ts-ranking-refuses-an-empty-relevant-set",
        claim="a query with nothing judged relevant is refused, not scored 0.0",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::refuses when no document is judged relevant",),
        edit=_delete_throw(
            '    throw new EmptyRelevantSet("no document is judged relevant for this query");'
        ),
    ),
    Mutation(
        name="ts-ranking-refuses-a-fractional-gain",
        claim="a relevance grade of 2.5 is refused, never silently rounded",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::refuses a fractional relevance gain rather than rounding it",),
        edit=_delete_throw(
            "      throw new InvalidRankingRequest(\n"
            "        `relevance gain for '${doc}' is not whole: ${gain}`,\n"
            "      );"
        ),
    ),
    Mutation(
        name="ts-ranking-refuses-a-duplicate-document",
        claim="a ranked list holding one document twice is refused, not de-duplicated",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=("src/ranking.test.ts::refuses a ranked list holding the same document twice",),
        edit=_delete_throw(
            "    throw new InvalidRankingRequest(\n"
            '      "ranked list holds the same document id twice",\n'
            "    );"
        ),
    ),
    Mutation(
        name="ts-metrics-threshold-is-inclusive",
        claim="a score exactly equal to the threshold is a POSITIVE prediction",
        target=_TS_METRICS,
        runner=_VITEST,
        guard=("src/metrics.test.ts::treats a score exactly equal to the threshold as positive",),
        edit=_replace_once(
            "    const predictedPositive = (yScore[index] as number) >= threshold;",
            "    const predictedPositive = (yScore[index] as number) > threshold;",
        ),
    ),
    Mutation(
        name="ts-metrics-fpr-is-not-fnr",
        claim="the false-alarm rate and the miss rate are different numbers",
        target=_TS_METRICS,
        runner=_VITEST,
        guard=(
            "src/metrics.test.ts::keeps the false-positive rate distinct from the "
            "false-negative rate",
        ),
        edit=_replace_once(
            "    falsePositiveRate: ratio(falsePositives, falsePositives + trueNegatives),",
            "    falsePositiveRate: ratio(falseNegatives, falseNegatives + truePositives),",
        ),
    ),
    Mutation(
        name="ts-metrics-zero-division-is-zero-not-nan",
        claim="an undefined rate reports 0, matching sklearn's zero_division, never NaN",
        target=_TS_METRICS,
        runner=_VITEST,
        guard=("src/metrics.test.ts::reports zero, not NaN, when nothing was predicted positive",),
        edit=_replace_once(
            "  return denominator === 0 ? 0 : numerator / denominator;",
            "  return numerator / denominator;",
        ),
    ),
    Mutation(
        name="ts-metrics-refuses-a-single-class",
        claim="a one-class input is refused here exactly as it is refused in Python",
        target=_TS_METRICS,
        runner=_VITEST,
        guard=("src/metrics.test.ts::refuses a single-class label set",),
        edit=_delete_throw(
            '    throw new InvalidScoreRequest("need both classes present for AUC metrics");'
        ),
    ),
    Mutation(
        name="ts-metrics-default-threshold-is-half",
        claim="the documented default decision threshold of 0.5 is the shipped one",
        target=_TS_METRICS,
        runner=_VITEST,
        guard=("src/metrics.test.ts::uses the documented default threshold of 0.5",),
        edit=_replace_once(
            "export const DEFAULT_THRESHOLD = 0.5;", "export const DEFAULT_THRESHOLD = 0.9;"
        ),
    ),
    # ----------------------------------------------------------------------------------
    # The cross-language pin itself. The two mutations below are guarded ONLY by the
    # shared-vector suite, so they answer the question that makes the vectors worth
    # having: if TypeScript's answer drifts away from Python's, does the shared file
    # actually notice? A vector suite nobody has watched fail is decoration.
    # ----------------------------------------------------------------------------------
    Mutation(
        name="ts-cells-match-pythons-sklearn",
        claim="a transposed confusion cell is caught by the vectors Python also replays",
        target=_TS_METRICS,
        runner=_VITEST,
        guard=(
            "src/metricVectors.test.ts::vector one_error_of_each_kind: "
            "the four confusion cells match",
        ),
        edit=_replace_once("      falseNegatives += 1;", "      falsePositives += 1;"),
    ),
    Mutation(
        name="ts-ranking-matches-pythons-trec-eval",
        claim="a recall denominator that drifts from trec_eval's is caught by the vectors",
        target=_TS_RANKING,
        runner=_VITEST,
        guard=(
            "src/metricVectors.test.ts::vector graded_gains_and_a_zero_gain_judgment: "
            "every ranking metric matches",
        ),
        edit=_replace_once(
            "  return Object.values(relevant).filter((gain) => gain > 0).length;",
            "  return Object.values(relevant).length;",
        ),
    ),
    Mutation(
        name="documented-metric-vector-count-is-22",
        claim="the README's 6 ranking + 7 ranking-refusal + 5 classification + 4 "
        "classification-refusal shared metric cases are all still shipped",
        target=_METRIC_VECTORS,
        guard=(
            "tests/test_documented_constants.py::test_the_metric_vector_counts_the_readme_promises",
        ),
        edit=_drop_last_metric_vector,
    ),
)


@dataclass(frozen=True)
class Result:
    """One mutation's two exit codes, and what they mean."""

    mutation: Mutation
    before: int
    after: int

    @property
    def held(self) -> bool:
        """The guard was green, then went red. Nothing else counts."""
        return self.before == _ALL_PASSED and self.after == _TESTS_FAILED

    @property
    def verdict(self) -> str:
        if self.before != _ALL_PASSED:
            return f"BASELINE NOT GREEN (exit {self.before}) — the guard was not passing to start"
        if self.after == _TESTS_FAILED:
            return "RED — the guard fired"
        if self.after == _ALL_PASSED:
            return "SURVIVED — the guard is blind to this break"
        if self.after == _NOTHING_COLLECTED:
            return "NOTHING COLLECTED — the named guard does not exist"
        return f"CRASHED (exit {self.after}) — not evidence either way"


def _pytest(node_ids: Sequence[str]) -> int:
    """Run pytest and return ONLY its exit code — stdout is for the reader, not the verdict.

    ``--no-cov`` because addopts carry a 90% coverage floor: a subset of the suite would
    exit 1 on coverage alone, and "red" would stop meaning "the guard fired"."""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "--no-cov", "-p", "no:cacheprovider", "-q", *node_ids],
        cwd=_ROOT,
        check=False,
    )
    return completed.returncode


def _split_guards(guard: Sequence[str]) -> tuple[list[str], str]:
    """``file::test name`` pairs -> (unique files, one alternation pattern).

    The names are regex-escaped because ``--testNamePattern`` is a JavaScript RegExp:
    an unescaped ``(`` in a test title would silently change which tests match."""
    files, names = [], []
    for entry in guard:
        path, _, name = entry.partition("::")
        if path not in files:
            files.append(path)
        names.append(_escape_for_js_regex(name))
    return files, "|".join(names)


def _escape_for_js_regex(name: str) -> str:
    return "".join(f"\\{ch}" if ch in "()[]{}.*+?^$|/\\" else ch for ch in name)


def _vitest_counts(report: Path) -> tuple[int, int]:
    """Read (passed, failed) out of the JSON reporter's output.

    A missing or unparseable file means the runner never produced a report — a
    misspelled reporter name does exactly that, and it is the failure mode that once
    let a sibling harness score twelve crashed runs as green. It raises here."""
    if not report.exists():
        raise HarnessError(f"vitest wrote no JSON report to {report}; no verdict is possible")
    data = json.loads(report.read_text(encoding="utf-8"))
    return int(data["numPassedTests"]), int(data["numFailedTests"])


def _vitest_verdict(passed: int, failed: int) -> int:
    """Map vitest's counts onto pytest's exit codes, so one report holds both.

    ``vitest run -t <no match>`` exits 0 with every test in the file counted as
    "total" and none of them run, so the exit code cannot distinguish a passing guard
    from an absent one. Zero passes and zero failures means nothing ran."""
    if failed > 0:
        return _TESTS_FAILED
    if passed == 0:
        return _NOTHING_COLLECTED
    return _ALL_PASSED


def _vitest_command(files: Sequence[str], pattern: str, report: Path) -> list[str]:
    """``pnpm`` is resolved from PATH on purpose — it is the pinned package manager for
    ``ts/``, and hardcoding a machine-specific absolute path would break every runner."""
    return [
        "pnpm",
        "exec",
        "vitest",
        "run",
        *files,
        "--testNamePattern",
        pattern,
        "--reporter=json",
        f"--outputFile={report}",
    ]


def _vitest(guard: Sequence[str]) -> int:
    """Run the named vitest guards and return a pytest-shaped exit code."""
    files, pattern = _split_guards(guard)
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "vitest.json"
        subprocess.run(  # noqa: S603
            _vitest_command(files, pattern, report), cwd=_TS, check=False
        )
        return _vitest_verdict(*_vitest_counts(report))


def _run_guard(mutation: Mutation) -> int:
    return _vitest(mutation.guard) if mutation.runner == _VITEST else _pytest(mutation.guard)


def _invalidate_bytecode(path: Path) -> None:
    """Delete the cached ``.pyc`` beside a source file this harness just rewrote.

    CPython decides a ``.pyc`` is current from the source's **mtime and size**, and
    several mutations here are deliberately one character for one character — ``P @ k``
    -> ``P @ 1``, ``R @ k`` -> ``P @ k``, ``AP)`` -> ``RR)``. The size never changes, so
    when the write lands inside the same mtime tick as the existing ``.pyc`` the next
    interpreter loads the STALE bytecode: the guard runs against code that was never
    mutated, passes, and is scored ``SURVIVED``.

    The restore path needs it just as badly, and for a nastier reason. The ``.pyc``
    written while the file was mutated can shadow the restored source, so the NEXT
    mutation's baseline would run mutated bytecode and the whole report drifts.

    This was not theoretical: ``ranking-k-reaches-trec-eval`` was scored ``SURVIVED`` on
    two of three consecutive runs at an unchanged commit before this call existed."""
    if path.suffix != ".py":
        return
    for pyc in (path.parent / "__pycache__").glob(f"{path.stem}.*.pyc"):
        pyc.unlink()


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    _invalidate_bytecode(path)


def _apply(path: Path, mutation: Mutation, original: str) -> None:
    """Mutate the file, then read it back off disk to prove the mutation landed."""
    mutated = mutation.edit(original)
    if mutated == original:
        raise MutationNotAppliedError("the edit produced identical text")
    _write(path, mutated)
    if path.read_text(encoding="utf-8") != mutated:
        raise MutationNotAppliedError(f"{mutation.target} on disk does not hold the mutation")


def _restore(path: Path, original: str) -> None:
    _write(path, original)
    if path.read_text(encoding="utf-8") != original:
        raise MutationNotAppliedError(f"restore failed: {path} does not match its original bytes")


def _check(mutation: Mutation) -> Result:
    path = _ROOT / mutation.target
    original = path.read_text(encoding="utf-8")
    print(f"\n>>> {mutation.name}\n    claim:  {mutation.claim}\n    break:  {mutation.target}")
    before = _run_guard(mutation)
    try:
        _apply(path, mutation, original)
        after = _run_guard(mutation)
    finally:
        _restore(path, original)
    return Result(mutation=mutation, before=before, after=after)


def _targets() -> tuple[str, ...]:
    return tuple(sorted({mutation.target for mutation in MUTATIONS}))


def _require_clean_targets() -> bool:
    """Refuse to edit a file that already has uncommitted work in it."""
    completed = subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain", "--", *_targets()],  # noqa: S607
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return True
    print(f"REFUSING: uncommitted changes in files this harness edits:\n{completed.stdout}")
    return False


def _report(results: Sequence[Result]) -> None:
    print("\n" + "=" * 108)
    print(f"{'mutation':<44}{'before':>8}{'after':>7}   verdict")
    print("-" * 108)
    for result in results:
        print(f"{result.mutation.name:<44}{result.before:>8}{result.after:>7}   {result.verdict}")
    print("=" * 108)


def _restore_note(restored: int) -> str:
    return "green" if restored == _ALL_PASSED else "NOT GREEN"


def _summarise(results: Sequence[Result], restored: int) -> int:
    """Exit non-zero if any guard survived its break, or if restore left the suite red."""
    fired = [result for result in results if result.held]
    print(f"\n{len(fired)}/{len(results)} guards fired when their claim was broken.")
    print(f"whole suite after restore: exit {restored} ({_restore_note(restored)})")
    if len(fired) < len(results):
        return _TESTS_FAILED
    return restored


def main() -> int:
    if not _require_clean_targets():
        return _TESTS_FAILED
    print("baseline — the whole suite, unmutated")
    if _pytest(()) != _ALL_PASSED:
        print("REFUSING: the suite is not green before any mutation is applied.")
        return _TESTS_FAILED
    results = [_check(mutation) for mutation in MUTATIONS]
    _report(results)
    print("\ngreen after restore — the whole suite again")
    return _summarise(results, _pytest(()))


if __name__ == "__main__":
    raise SystemExit(main())
