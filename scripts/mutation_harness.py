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

Run it::

    uv run poe mutants

It edits tracked files in place, so it refuses to start unless every file it will touch
is clean in git.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# pytest's documented exit codes. The verdict is read from these and from nothing else.
_ALL_PASSED = 0
_TESTS_FAILED = 1
_NOTHING_COLLECTED = 5

# A one-item file has nothing to drop, so the vector-count mutation could not apply.
_MIN_VECTORS_TO_DROP_ONE = 2

_RANKING = "src/assay/ranking.py"
_ENVELOPE = "src/avow/envelope.py"
_LEDGER = "src/avow/ledger.py"
_SETTINGS = "src/assay/settings.py"
_VECTORS = "testdata/vectors/canonical.json"
_PNPM_WORKSPACE = "ts/pnpm-workspace.yaml"


class MutationNotAppliedError(RuntimeError):
    """The edit did not reach the file, so its result would prove nothing."""


@dataclass(frozen=True)
class Mutation:
    """One break, the claim it breaks, and the tests that must notice."""

    name: str
    claim: str
    target: str
    guard: tuple[str, ...]
    edit: Callable[[str], str]


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


def _apply(path: Path, mutation: Mutation, original: str) -> None:
    """Mutate the file, then read it back off disk to prove the mutation landed."""
    mutated = mutation.edit(original)
    if mutated == original:
        raise MutationNotAppliedError("the edit produced identical text")
    path.write_text(mutated, encoding="utf-8")
    if path.read_text(encoding="utf-8") != mutated:
        raise MutationNotAppliedError(f"{mutation.target} on disk does not hold the mutation")


def _restore(path: Path, original: str) -> None:
    path.write_text(original, encoding="utf-8")
    if path.read_text(encoding="utf-8") != original:
        raise MutationNotAppliedError(f"restore failed: {path} does not match its original bytes")


def _check(mutation: Mutation) -> Result:
    path = _ROOT / mutation.target
    original = path.read_text(encoding="utf-8")
    print(f"\n>>> {mutation.name}\n    claim:  {mutation.claim}\n    break:  {mutation.target}")
    before = _pytest(mutation.guard)
    try:
        _apply(path, mutation, original)
        after = _pytest(mutation.guard)
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
