# Trust-Kernel (Avow / Assay / Writ) Portfolio Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Consumer phases P2–P6 are file-disjoint across five
> repos — dispatch them as CONCURRENT worktree agents per the fan-out rule.

**Goal:** Finish the trust-kernel Legos (Avow envelope, Assay scoring face, Writ effect face),
package them as installable units for both CPython and the browser, wire each into its live
consumer project (AlmaMesh, AML-Filter, EdgeReco, Personal-Finances, Privacy-Core), and deploy
everything to the northstar bar.

**Architecture:** One repo (renamed `assay` → `avow`) ships one PyPI distribution `avow` exposing
three top-level import packages (`avow` = the signed-receipt envelope, `assay` = scoring face,
`writ` = effect face) with the heavy scoring deps behind an extra, plus one npm package
`@edgeproc/avow` (TS RFC-8785 canonicalizer + Ed25519 sign/verify) kept byte-compatible by a
shared golden-vector conformance suite. Native/CPython consumers import the Python kernel
directly; Pyodide (AlmaMesh) micropip-installs the same wheel (pynacl is in the Pyodide lock);
pure-TS browser consumers (AML-Filter, Privacy-Core, EdgeReco demo) use `@edgeproc/avow`.

**Tech Stack:** Python 3.13 / uv / hatchling / pydantic / pynacl / rfc8785; TypeScript / pnpm /
`@noble/ed25519@^3.1` / `canonicalize@^3`; Cloudflare Pages deploys via existing GH Actions.

## Ground truth this plan is built on (verified 2026-07-19)

- `~/dev/oss/assay` is on `main`, gate green (81 tests; poe gate = ruff + format + mypy strict +
  xenon A + pytest ≥90%; CI mirrors gate; weekly pip-audit workflow). It holds all three faces
  under `src/assay/`: `receipt.py` (generic `SignedReceipt[SubjectT]`, `sign_payload`,
  `verify_signature` with pinned-key check), `canonical.py` (rfc8785 JCS + `sha256:<hex>`
  content hash), `keys.py` (pynacl, 32-byte seed, 0600), `verify.py`, `ledger.py` (JSONL append +
  integrity), `writ.py` (`EffectSubject`, `gate`, `KeyholderEffector`, `governed_gate`), plus the
  scoring face (`api.py`, `metrics.py`, `calibration.py`, `uncertainty.py`, `composite.py`,
  `models.py`, `cli.py`, `errors.py`, `settings.py`).
- **PyPI names:** `avow` AVAILABLE; `assay` TAKEN (Brandon Rhodes); `writ` TAKEN. → the
  distribution must be named `avow`; import-package names are free.
- **Pyodide:** `pynacl`, `pydantic`, `pydantic-core`, `cryptography` are all in the Pyodide
  0.27.2 `pyodide-lock.json`. `rfc8785` is pure Python (micropip-installable from PyPI). The
  Python kernel therefore runs unmodified in Pyodide — **no crypto rewrite needed for AlmaMesh**.
- **TS precedent:** `amlfilter-browser/src/engine/crypto.ts` already ships fail-closed
  `verifyEd25519` on `@noble/ed25519@^3.1` with a WebCrypto-Ed25519 fast path; npm
  `canonicalize@3.0.0` is the RFC-8785 (JCS) reference implementation.
- Consumer seams (all confirmed in code): AlmaMesh
  `backend/src/almamesh/domains/strength_summary.py::strength_summary` (headline `strength_pct`,
  min of `shadbala_pct`/`sav_pct`), mirrored at
  `frontend/packages/browser/src/pyodide/predictive.ts`; AML-Filter
  `amlfilter-browser/src/engine/sequenceMatcher.ts` (`TieredMatch.score` + `MatchTier`) and
  `amlfilter-workstation/src/review.ts` (`resolve` + `ResolutionStatus` + `MatchEvent`);
  EdgeReco `backend/src/edgereco/reco/scorer.py::score_product` (weighted components dict from
  bundle-carried `RankingConfig`); Personal-Finances
  `backend/packages/finance_engine/decorators.py::_emit_audit_record` (append-only `audit.log`);
  Privacy-Core `src/egress.ts` (`approve()` → `RedactedPayload`, `guardedProvider`).

## The three governing decisions

### D1 — Packaging: one repo, one PyPI dist (`avow`) + one npm package (`@edgeproc/avow`)

**Decision:** Keep a single repo, renamed `assay` → `avow` on GitHub (auto-redirects old URLs).
One PyPI distribution **`avow`** exposing three top-level import packages:

- `avow` — the envelope: `envelope.py` (generic `SignedReceipt`), `canonical.py`, `keys.py`,
  `verify.py`, `ledger.py`, `errors.py`, `settings.py`. Base deps only: `pydantic`,
  `pydantic-settings`, `pynacl`, `rfc8785`.
- `assay` — the scoring face, `import avow`. Heavy deps (`scikit-learn`, `scipy`, `numpy`)
  behind extra **`avow[assay]`**; `typer` behind **`avow[cli]`**.
- `writ` — the effect face, `import avow`. No extra deps.

npm ships **`@edgeproc/avow`** (TS receipt types + JCS canonical bytes + Ed25519 sign/verify)
from `ts/` in the same repo, sharing `testdata/vectors/` with the Python tests.

**Why (and why not three dists):** (1) PyPI reality — `assay` and `writ` are squatted, so three
independently-named dists are impossible; import names need no registry and stay clean. (2) The
dependency edges the task requires (assay→avow, writ→avow) become *import* edges inside one
wheel, enforced by an import-linter contract instead of version pins — zero lockstep-versioning
overhead, one CI, one release. (3) Pyodide/browser weight is solved by the extras split: micropip
installs base `avow` (pydantic + pynacl + rfc8785, all available) without ever pulling sklearn.
(4) Least churn: a `git mv` refactor inside the existing green repo, no new repos, no workspace
machinery. Repo renames to `avow` because the kernel/umbrella is Avow in the spine
(`… → Avow → {Assay, Writ} → consumers`) and the dist name must match what `pip install` says.

### D2 — Native-vs-browser crypto (the crux)

**Decision:** `pynacl` **works in Pyodide** (present in the official 0.27 lockfile), so AlmaMesh
runs the *actual Python kernel* in-browser: `micropip.install("avow")` pulls the pure-Python
wheel; `pyodide.loadPackage(["pynacl", "pydantic"])` supplies the binary deps. For pure-TS
consumers the browser path is `@edgeproc/avow`: canonical bytes via `canonicalize` (RFC 8785),
Ed25519 via `@noble/ed25519` (portfolio precedent: aml-filter's `crypto.ts`, with its
WebCrypto-when-available fast path lifted into the Lego). Cross-language byte identity is
**gated, not assumed**: a golden-vector suite (`testdata/vectors/*.json`) generated by Python and
replayed by TS asserts identical canonical bytes, identical `sha256:` hashes, and that a
Python-signed receipt verifies in TS and a TS-signed receipt verifies in Python. RFC 8785 number
serialization (ECMAScript shortest round-trip) is the known hazard — vectors must include floats
(`0.5`, `0.1`, `1e21`, `-0.0`) and reject any divergence in CI.

**Who signs vs who verifies (minimizing cross-language signing):**

| Consumer | Signs | Verifies | Rationale |
|---|---|---|---|
| AlmaMesh | Pyodide (Python kernel, in-browser) | same | local-first app; the Python kernel runs where the score is computed — no port |
| AML-Filter | **TS** (workstation, per-installation key) | TS | the reviewer's allow/deny decision *happens* in-browser (no server exists); unavoidable TS signing |
| EdgeReco | Python (backend, at bundle build) | TS (browser demo) + Python | scores are produced server/build-side; browser only needs verify |
| Personal-Finances | Python (localhost CPython) | Python CLI | native end to end |
| Privacy-Core | TS (egress approval is a browser event) | TS | pure-TS library |

Browser key custody (AML-Filter, Privacy-Core): per-installation Ed25519 seed generated locally,
stored in OPFS (AML-Filter's existing storage tier); documented honestly as *same-origin-readable*
— the same capability-holding caveat Writ's v0 docstring already states. No custody overclaim.

### D3 — Northstar bar (applies to every artifact this plan touches)

Full test pyramid (unit + integration + cross-language conformance + live e2e where a site
exists); remote CI green on main; Karpathy docs (teen-readable README front door + expert
section, runnable quickstart, why-before-how); coded errors (Python: `avow.errors` catalog; TS:
coded error classes, i18n keys on deployed sites); no hardcoded config (pydantic-settings /
typed env); security (0600 seeds, pinned keys, weekly pip-audit, no secrets in code); and
**live-verified deploy** — drive the real site in a real browser and watch the receipt verify.

## Global constraints

- Python ≥3.13; uv-managed; `uv run poe gate` green is the merge floor in every Python repo.
- pnpm (never npm/bun) in every JS repo; existing per-repo gates (vitest/playwright) stay green.
- TDD: red → green → commit for every code task; bug fixes start with a failing test.
- Coverage ≥90% on kernel logic (existing pytest gate) — new modules included.
- `@noble/ed25519` pinned `^3.1.0`, `canonicalize` pinned `^3.0.0`.
- edge-proc stays purely a dependency — never name portfolio consumers inside avow docs beyond
  generic examples; avow docs may name its consumers (avow is the kernel, not edge-proc).
- Deployed-site changes carry i18n keys for any new user-facing strings.
- Branch discipline: one short-lived branch per phase per repo; merged-to-main-then-deleted.
- Diagrams are d2/text, never mermaid.
- **Human-gated (hand to Harish, never automate):** GitHub repo rename `assay`→`avow`; PyPI
  publish of `avow`; npm publish of `@edgeproc/avow` and `@edgeproc/privacy-core`; merging PRs;
  prod Cloudflare Pages deploys; any repo-visibility flip; any new CI secret.

## Phase map (dependencies and parallelism)

```text
P0 kernel split+packaging (avow repo)          — serial, first
P1 TS Lego + conformance vectors (avow repo)   — after P0 (needs vectors from P0 layout)
P2 AlmaMesh   ┐
P3 AML-Filter │
P4 EdgeReco   ├ after P1; file-disjoint repos — run as CONCURRENT worktree agents
P5 Personal-Finances (needs only P0)
P6 Privacy-Core ┘
P7 Deploy + live-verify + publish              — after P2..P6, serial (human gates)
```

**Total: 8 phases.** P0/P1 serialize; P2–P6 fan out concurrently; P7 closes.

## File structure (target)

```text
~/dev/oss/avow   (renamed from assay)
├── pyproject.toml                 # dist name avow, extras [assay] [cli]
├── src/avow/                     # envelope: envelope.py canonical.py keys.py verify.py
│                                  #   ledger.py errors.py settings.py __init__.py _version.py
├── src/assay/                    # scoring face: api.py metrics.py calibration.py
│                                  #   uncertainty.py composite.py models.py cli.py errors.py
├── src/writ/                     # effect face: gate.py (from writ.py) errors.py __init__.py
├── ts/                            # @edgeproc/avow: src/{types,canonical,keys,receipt,errors}.ts
├── testdata/vectors/              # golden vectors shared by Python + TS conformance tests
└── tests/                         # existing suite, re-pathed + conformance generators
```

---

## Phase P0 — Kernel: split into avow / assay / writ, repackage as dist `avow`

### Task P0.1: Move the envelope to `src/avow/` and re-point imports

**Files:**
- Create: `src/avow/__init__.py`, `src/avow/envelope.py` (from `src/assay/receipt.py` minus the
  score-face subject), `src/avow/canonical.py`, `src/avow/keys.py`, `src/avow/verify.py`,
  `src/avow/ledger.py`, `src/avow/errors.py` (envelope errors: `SignatureInvalid`,
  `ReplayMismatch`, `CanonicalizationFailed`, `LedgerIntegrityError`), `src/avow/settings.py`,
  `src/avow/_version.py`
- Modify: `src/assay/receipt.py` → keeps only `ReceiptPayload`/`ClassificationDetail`/
  `CalibrationDetail`/`CompositeDetail`/`ScoreReceipt = SignedReceipt[ReceiptPayload]`, importing
  the envelope from `avow`
- Test: `tests/test_envelope_split.py`

**Interfaces:**
- Consumes: current `assay.receipt` / `assay.canonical` / `assay.keys` / `assay.verify` /
  `assay.ledger` bodies (verbatim moves — behavior must not change).
- Produces: `from avow import SignedReceipt, sign_payload, verify_signature, payload_digest,
  canonical_bytes, content_hash, generate_signing_key, load_signing_key, save_signing_key,
  public_key_hex` — the exact names every later phase imports.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_envelope_split.py
"""The envelope is importable from avow with zero scoring-face deps loaded."""
import sys


def test_avow_exports_envelope() -> None:
    from avow import (
        SignedReceipt, sign_payload, verify_signature, payload_digest,
        canonical_bytes, content_hash, generate_signing_key, public_key_hex,
    )
    assert SignedReceipt is not None and callable(sign_payload)


def test_avow_import_does_not_pull_sklearn() -> None:
    for mod in [m for m in sys.modules if m.startswith(("sklearn", "scipy"))]:
        del sys.modules[mod]
    import importlib
    import avow
    importlib.reload(avow)
    assert not any(m.startswith(("sklearn", "scipy")) for m in sys.modules)


def test_score_receipt_roundtrip_unchanged() -> None:
    from avow import generate_signing_key, public_key_hex, sign_payload, verify_signature
    from assay.receipt import ReceiptPayload
    key = generate_signing_key()
    payload = ReceiptPayload(
        assay_version="0", metric="f1", metric_version="1", inputs_hash="sha256:0", score=0.5
    )
    receipt = sign_payload(payload, key)
    verify_signature(receipt, expected_public_key=public_key_hex(key))
```

- [ ] **Step 2: Run it to fail** — `uv run pytest tests/test_envelope_split.py -x` →
  FAIL `ModuleNotFoundError: No module named 'avow'`.
- [ ] **Step 3: `git mv` the five envelope modules into `src/avow/` (rename `receipt.py` →
  `envelope.py`, leaving the four score-subject models + `ScoreReceipt` alias behind in
  `src/assay/receipt.py`), split `errors.py` (envelope codes → `avow/errors.py`, scoring codes
  stay), write `src/avow/__init__.py` re-exporting the Produces list, and mechanical-replace
  `from assay.canonical|keys|verify|ledger import` → `from avow.… import` across `src/` and
  `tests/`.** `src/assay/__init__.py` keeps its public API unchanged (re-export from avow where
  needed) so nothing downstream breaks.
- [ ] **Step 4: Full gate green** — `uv run poe gate` (mypy strict must pass on the new
  packages; add `src/avow`, `src/writ` to the typecheck target).
- [ ] **Step 5: Commit** — `git commit -m "refactor: extract avow envelope package from assay"`.

### Task P0.2: Move Writ to `src/writ/`

**Files:**
- Create: `src/writ/__init__.py` (exports `EffectRequest`, `EffectSubject`, `Decision`,
  `Policy`, `gate`, `KeyholderEffector`, `governed_gate`, `EffectReceipt`), `src/writ/gate.py`
  (body of current `src/assay/writ.py`, imports from `avow`)
- Delete: `src/assay/writ.py`
- Test: `tests/test_writ.py` (re-point imports `assay.writ` → `writ`)

**Interfaces:**
- Consumes: `avow.SignedReceipt`, `avow.sign_payload` (Task P0.1).
- Produces: `from writ import gate, governed_gate, EffectSubject, EffectRequest,
  KeyholderEffector`; `EffectReceipt = SignedReceipt[EffectSubject]`.

- [ ] **Step 1:** Update `tests/test_writ.py` imports to `from writ import …`; run
  `uv run pytest tests/test_writ.py -x` → FAIL `ModuleNotFoundError: No module named 'writ'`.
- [ ] **Step 2:** `git mv src/assay/writ.py src/writ/gate.py`; fix its imports
  (`assay.receipt` → `avow`); add `src/writ/__init__.py` with the exports above plus
  `EffectReceipt` alias.
- [ ] **Step 3:** `uv run poe gate` → green. Commit
  `"refactor: writ is its own top-level package on the avow envelope"`.

### Task P0.3: Repackage — dist name `avow`, three packages, extras, guarded imports

**Files:**
- Modify: `pyproject.toml`, `src/assay/api.py` (guarded heavy-dep import), `src/assay/errors.py`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Produces: `pip install avow` → `import avow, writ` works with base deps;
  `pip install 'avow[assay]'` → `import assay` scoring works; `avow[cli]` → `assay` CLI.

- [ ] **Step 1: Failing test**

```python
# tests/test_packaging.py
import tomllib
from pathlib import Path


def test_dist_is_avow_with_three_packages_and_extras() -> None:
    cfg = tomllib.loads(Path("pyproject.toml").read_text())
    assert cfg["project"]["name"] == "avow"
    assert set(cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]) == {
        "src/avow", "src/assay", "src/writ"
    }
    base = " ".join(cfg["project"]["dependencies"])
    assert "scikit-learn" not in base and "pynacl" in base and "rfc8785" in base
    extras = cfg["project"]["optional-dependencies"]
    assert any("scikit-learn" in d for d in extras["assay"])
    assert any("typer" in d for d in extras["cli"])
```

- [ ] **Step 2:** Run → FAIL (name is `assay`, no extras).
- [ ] **Step 3:** Edit `pyproject.toml`: `name = "avow"`; base `dependencies = [pydantic,
  pydantic-settings, pynacl, rfc8785]`; `[project.optional-dependencies] assay = ["scikit-learn>=1.9",
  "scipy>=1.18", "numpy>=2.5"]`, `cli = ["typer>=0.27"]`; wheel packages = the three `src/*`;
  version path → `src/avow/_version.py`; script `assay = "assay.cli:app"` stays (guarded). In
  `src/assay/__init__.py` wrap the sklearn-dependent surface in a guarded import that raises the
  coded error `ScoringExtraMissing("install avow[assay] to use the scoring face")` on
  `ModuleNotFoundError` — never a bare traceback.
- [ ] **Step 4:** `uv sync && uv run poe gate` green; plus a wheel smoke:
  `uv build && uv run --isolated --no-project --with dist/avow-*.whl python -c "import avow, writ"`.
- [ ] **Step 5:** Commit `"feat: package as dist 'avow' with assay/cli extras"`.

### Task P0.4: Golden-vector generator (the cross-language contract)

**Files:**
- Create: `tests/gen_vectors.py` (invoked via `uv run python tests/gen_vectors.py`),
  `testdata/vectors/canonical.json`, `testdata/vectors/receipts.json`
- Test: `tests/test_vectors.py`

**Interfaces:**
- Produces: `testdata/vectors/canonical.json` — list of `{name, payload, canonical_hex,
  content_hash}`; `testdata/vectors/receipts.json` — `{seed_hex, public_key, receipts: [{payload,
  payload_hash, signature}]}` signed with a FIXED TEST-ONLY seed (`b"\x01" * 32` — documented as
  non-secret). P1's TS suite replays both files byte-for-byte.

- [ ] **Step 1: Failing test**

```python
# tests/test_vectors.py
import json
from pathlib import Path

from avow import canonical_bytes, content_hash, verify_signature, SignedReceipt
from pydantic import BaseModel, ConfigDict


class _Subject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: str
    score: float
    tags: tuple[str, ...]


def test_canonical_vectors_replay() -> None:
    vectors = json.loads(Path("testdata/vectors/canonical.json").read_text())
    assert len(vectors) >= 8  # incl. floats 0.5, 0.1, 1e21, -0.0, unicode, nesting
    for v in vectors:
        assert canonical_bytes(v["payload"]).hex() == v["canonical_hex"]
        assert content_hash(v["payload"]) == v["content_hash"]


def test_receipt_vectors_verify() -> None:
    data = json.loads(Path("testdata/vectors/receipts.json").read_text())
    for r in data["receipts"]:
        receipt = SignedReceipt[_Subject](
            payload=_Subject(**r["payload"]), payload_hash=r["payload_hash"],
            public_key=data["public_key"], signature=r["signature"],
        )
        verify_signature(receipt, expected_public_key=data["public_key"])
```

- [ ] **Step 2:** Run → FAIL (no vectors). **Step 3:** Write `tests/gen_vectors.py` emitting the
  two files deterministically (payload set MUST include: empty object, key-order shuffle,
  unicode `"hélloé"`, floats `0.5, 0.1, 1e21, -0.0, 1e-7`, ints, nested arrays/objects,
  `null`/bools); run it; test green. **Step 4:** `uv run poe gate`; commit
  `"feat: cross-language golden vectors for canonical bytes + receipts"`.

### Task P0.5: Kernel docs + repo rename prep (northstar)

**Files:**
- Modify: `README.md` (front door: what/why in teen-readable terms, quickstart for all three
  faces, expert section; name everywhere is **avow**), `docs/ARCHITECTURE.md` (three packages,
  d2 diagram, native-vs-browser section from D2), `CHANGELOG.md`, `QUICKSTART.md`
- Test: `tests/test_demo_runs.py` (existing) still green; README quickstart commands executed
  verbatim in a fresh venv

- [ ] **Step 1:** Rewrite docs; every quickstart block copy-paste-run verified locally.
- [ ] **Step 2:** `uv run poe gate` + run both demos. Commit `"docs: avow kernel front door"`.
- [ ] **Step 3 (HUMAN GATE):** Hand Harish the rename + remote update commands:
  `gh repo rename avow -R hseshadr/assay` then `git remote set-url origin
  git@github.com:hseshadr/avow.git`; update `[project.urls]` in a follow-up commit.

---

## Phase P1 — `@edgeproc/avow` TS Lego + conformance gate (in avow repo, `ts/`)

### Task P1.1: Package scaffold + canonical bytes

**Files:**
- Create: `ts/package.json` (name `@edgeproc/avow`, deps `@noble/ed25519@^3.1.0`,
  `canonicalize@^3.0.0`; dev vitest + tsc; pnpm), `ts/tsconfig.json`, `ts/src/canonical.ts`,
  `ts/src/errors.ts`, `ts/src/index.ts`
- Test: `ts/src/canonical.test.ts`

**Interfaces:**
- Produces: `canonicalBytes(payload: JsonValue): Uint8Array`;
  `contentHash(payload: JsonValue): Promise<string>` returning `"sha256:<hex>"`; coded error
  class `CanonicalizationFailed`.

- [ ] **Step 1: Failing test — replay the Python vectors**

```typescript
// ts/src/canonical.test.ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { canonicalBytes, contentHash } from "./canonical";

const vectors = JSON.parse(
  readFileSync(new URL("../../testdata/vectors/canonical.json", import.meta.url), "utf8"),
);

describe("RFC-8785 byte identity with Python rfc8785", () => {
  for (const v of vectors) {
    it(`vector: ${v.name}`, async () => {
      expect(Buffer.from(canonicalBytes(v.payload)).toString("hex")).toBe(v.canonical_hex);
      expect(await contentHash(v.payload)).toBe(v.content_hash);
    });
  }
});
```

- [ ] **Step 2:** `pnpm vitest run` → FAIL. **Step 3:** Implement `canonical.ts` on
  `canonicalize` + `TextEncoder` + WebCrypto `crypto.subtle.digest("SHA-256", …)` (hex like
  aml-filter's `sha256Hex`). **Step 4:** green — this test IS the D2 gate; any float divergence
  fails here, not in production. **Step 5:** Commit `"feat(ts): @edgeproc/avow canonical bytes,
  vector-gated against Python"`.

### Task P1.2: Receipt sign/verify + keys

**Files:**
- Create: `ts/src/receipt.ts`, `ts/src/keys.ts`
- Test: `ts/src/receipt.test.ts`

**Interfaces:**
- Produces: `type SignedReceipt<S> = { payload: S; payload_hash: string; public_key: string;
  signature: string }`; `signPayload<S>(payload: S, seedHex: string): Promise<SignedReceipt<S>>`;
  `verifySignature<S>(receipt: SignedReceipt<S>, expectedPublicKey: string): Promise<void>`
  (throws coded `SignatureInvalid` / `ReplayMismatch` — pinned-key check FIRST, mirroring
  Python's `verify_signature` exactly); `generateSeedHex(): string`.

- [ ] **Step 1: Failing tests** — (a) replay `testdata/vectors/receipts.json`: every
  Python-signed receipt verifies in TS; (b) TS-signed receipt with the fixed test seed produces
  the byte-identical signature listed in the vectors (Ed25519 is deterministic — this closes the
  loop both directions without a Python-side run); (c) tampered payload → `ReplayMismatch`;
  wrong pinned key → `SignatureInvalid`.
- [ ] **Step 2:** red → implement on `@noble/ed25519` (`signAsync`/`verifyAsync`, hex helpers) →
  green. **Step 3:** `pnpm tsc --noEmit && pnpm vitest run`; wire `ts/` into repo CI as a second
  job. Commit `"feat(ts): receipt sign/verify byte-compatible with Python kernel"`.

### Task P1.3: TS docs + publish prep

- [ ] `ts/README.md` (quickstart: verify a receipt in 10 lines; the who-signs table from D2);
  `pnpm pack` smoke; version `0.1.0`. Commit. **npm publish is P7 (human gate).**

---

## Phase P2 — Wire AlmaMesh (Assay face, Pyodide, repo `~/dev/oss/almamesh`)

**Face:** Assay (ScoreReceipt over the calibrated strength %). **Mode:** Python-direct inside
Pyodide — micropip installs the `avow` wheel; `loadPackage(["pynacl", "pydantic"])` first.
**Deploy:** almamesh.com (CF Pages, existing workflow). **Effort M. Risks:** wheel availability
before PyPI publish (serve the wheel as a static asset from the site, signature-verified like the
existing almamesh wheel pipeline in `frontend/packages/browser/src/pyodide/runtime.ts`); Pyodide
package-load latency (lazy-load on first receipt request).

### Task P2.1: Backend — emit a ScoreReceipt beside `strength_summary`

**Files:**
- Create: `backend/src/almamesh/domains/strength_receipt.py`
- Modify: `backend/pyproject.toml` (dep `avow` via `[tool.uv.sources]` path during dev)
- Test: `backend/tests/domains/test_strength_receipt.py`

**Interfaces:**
- Consumes: `StrengthSummary` (existing: `strength_pct`, `shadbala_pct`, `sav_pct`, `band`,
  `key_graha`); `avow.sign_payload`; `assay.receipt.ReceiptPayload` shape as precedent but with
  an AlmaMesh subject.
- Produces: `strength_receipt(summary: StrengthSummary, natal_hash: str, key: SigningKey) ->
  SignedReceipt[StrengthSubject]` where `StrengthSubject` is frozen pydantic:
  `{engine_version, domain, method: "min(shadbala_pct, sav_pct)", shadbala_pct, sav_pct,
  strength_pct, inputs_hash}` — the no-fake-precision covenant now signed.

- [ ] **Step 1:** Failing test: build a `StrengthSummary` fixture, sign, assert
  `receipt.payload.strength_pct == min(shadbala_pct, sav_pct)`, verify with pinned key,
  tamper → `ReplayMismatch`. **Step 2:** red → implement (≤15-line functions, python-quality) →
  green. **Step 3:** repo gate green; commit.

### Task P2.2: Frontend — surface the receipt in the Pyodide worker + UI badge

**Files:**
- Modify: `frontend/packages/browser/src/pyodide/predictive.ts` (call the new Python entry via
  the existing worker protocol), `frontend/packages/browser/src/pyodide/runtime.ts` (add
  `pynacl` to the loadPackage set + avow wheel to the verified-wheel manifest),
  `frontend/packages/browser/src/pyodide/protocol.ts` (typed receipt message)
- Create: strength-receipt badge component beside the existing strength % display ("verified ✓"
  + receipt JSON download), i18n keys for its strings
- Test: extend `frontend/packages/browser/src/pyodide/__tests__/runtime.test.ts` + one
  Playwright e2e: open a domain view → receipt badge renders → downloaded receipt verifies with
  the site's published public key (verify in test via `@edgeproc/avow`)

- [ ] **Step 1:** failing worker-protocol unit test → **Step 2:** implement → **Step 3:**
  e2e against `pnpm build && pnpm preview` (prod-CSP preview per the previewProdCspPlugin
  pattern) → **Step 4:** gates green, commit, PR (merge = human gate).

---

## Phase P3 — Wire AML-Filter (Assay + Writ, TS, repo `~/dev/oss/aml-filter`)

**Face:** Assay (match score receipt) + Writ (signed allow/deny resolution — the strongest Writ
fit in the portfolio). **Mode:** TS via `@edgeproc/avow` (the app already depends on
`@noble/ed25519`). **Deploy:** aml-filter.com (CF Pages). **Effort L. Risks:** browser key
custody (per-installation seed in OPFS — document same-origin caveat honestly, mirror Writ's v0
docstring); UX surface in the workstation review flow; e2e breadth (existing playwright configs).

### Task P3.1: Score receipt at the match seam

**Files:**
- Create: `frontend/packages/amlfilter-browser/src/engine/scoreReceipt.ts`
- Modify: `frontend/packages/amlfilter-browser/package.json` (dep `@edgeproc/avow`, pnpm
  workspace/link during dev)
- Test: `frontend/packages/amlfilter-browser/src/engine/scoreReceipt.test.ts`

**Interfaces:**
- Consumes: `TieredMatch` (`score: number`, `tier: MatchTier`) from `sequenceMatcher.ts` /
  `types.ts`; `signPayload`/`verifySignature` from `@edgeproc/avow`.
- Produces: `matchScoreSubject(match: TieredMatch, watchlistVersion: string, inputsHash: string)`
  → frozen subject `{engine: "amlfilter-sequenceMatcher", engine_version, watchlist_version,
  inputs_hash, score, tier}`; `signMatchReceipt(subject, seedHex)` returning
  `SignedReceipt<MatchScoreSubject>`.

- [ ] Red (subject determinism + sign/verify/tamper tests) → green → commit.

### Task P3.2: Writ receipt on `resolve` + installation key custody

**Files:**
- Create: `frontend/packages/amlfilter-workstation/src/writReceipt.ts`,
  `frontend/packages/amlfilter-workstation/src/installKey.ts` (generate-once seed, persisted via
  the existing OPFS/SQLite store; export public key for the audit view)
- Modify: `frontend/packages/amlfilter-workstation/src/review.ts` — `resolve()` additionally
  seals `SignedReceipt<ResolutionSubject>` (`{action: "aml.resolution", target: customerId,
  args_digest: contentHash({matchIds, from, to}), decision: status, watchlist_version}`) and
  appends it to the `MatchEvent` audit trail (new event type `RESOLUTION_SEALED`)
- Test: `review.test.ts` additions + one e2e in `frontend/app/tests/e2e-c1/` — resolve a match,
  open audit trail, receipt verifies against the installation public key shown in Settings

- [ ] Red → green → repo gates (vitest + both playwright configs) → commit → PR (human merge).

---

## Phase P4 — Wire EdgeReco (Assay face, Python signs / TS verifies, repo `~/dev/oss/edge-reco`)

**Face:** Assay — the weighted composite in `backend/src/edgereco/reco/scorer.py::score_product`
(components dict + bundle-carried `RankingConfig`) is a natural `ScoreReceipt` with
`governed_by = ranking_config` semantics. **Mode:** backend Python signs at bundle-publish time
(`republish.py` path); the browser demo verifies via `@edgeproc/avow`. **Deploy:** edge-reco.com
(CF Pages). **Effort M. Risk:** keep receipt emission OUT of the hot per-request scoring loop —
sign the *ranking-config + sample-scores attestation* at publish time, not every request.

### Task P4.1: Backend — signed ranking attestation at publish

**Files:**
- Create: `backend/src/edgereco/reco/score_receipt.py`
- Modify: `backend/src/edgereco/republish.py` (emit `ranking_receipt.json` into the bundle),
  backend pyproject (dep `avow`, path source during dev)
- Test: `backend/tests/reco/test_score_receipt.py`

**Interfaces:**
- Consumes: `ScoringWeights` / `RankingConfig` (`ranking_config.py`), `score_product`,
  `avow.sign_payload`.
- Produces: `ranking_attestation(config: RankingConfig, golden_scores: dict[str, float]) ->
  SignedReceipt[RankingSubject]` — subject `{edgereco_version, ranking_config_hash:
  content_hash(config.model_dump()), golden_scores}` where `golden_scores` are `score_product`
  outputs over 3 fixed catalog fixtures (so a verifier replays the formula, not just the config).

- [ ] Red (attestation determinism; tamper on one weight flips `ranking_config_hash`;
  verify/tamper) → green → gate → commit.

### Task P4.2: Frontend demo — verify + show the attestation

**Files:**
- Modify: frontend demo bundle-load path to fetch `ranking_receipt.json`, verify with the
  pinned publisher key via `@edgeproc/avow`, render a "ranking weights verified" badge with
  receipt details (i18n keys)
- Test: vitest unit (verify fail-closed on tamper) + playwright e2e on preview

- [ ] Red → green → gates → commit → PR (human merge).

---

## Phase P5 — Wire Personal-Finances (Avow envelope, native CPython, repo `~/dev/oss/personal-finances`)

**Face:** Avow — upgrade the append-only `audit.log` (`finance_engine/decorators.py::
_emit_audit_record`) to a signed, verifiable ledger. Writ on write-actions stays future (the app
is read-only by covenant). **Mode:** Python-direct. **Deploy:** none (localhost app) — done =
merged to main + CI green. **Effort S. Risk:** none material; key lives beside the existing
Keychain-first posture (seed file under the app data dir, 0600 via `avow.keys`).

### Task P5.1: Signed audit ledger

**Files:**
- Create: `backend/packages/finance_engine/audit_receipt.py`
- Modify: `backend/packages/finance_engine/decorators.py` (`_emit_audit_record` signs the record
  into `avow.ledger.append` alongside the existing JSONL line), `config.py`
  (`audit_signing_key_path: Path` via pydantic-settings — no hardcoded path)
- Test: `backend/tests/unit/test_audit_receipt.py`

**Interfaces:**
- Consumes: the existing audit dict `{timestamp, event, tool, duration_ms, input_record_ids,
  output_record_ids}`; `avow` (`sign_payload`, `ledger.append`, `ledger.verify_integrity`,
  `load_signing_key`/`generate_signing_key`).
- Produces: `AuditSubject` frozen model over those exact fields (timestamp INCLUDED here — this
  ledger records events, not pure functions; determinism holds per-event, and integrity comes
  from hash+signature, matching `avow.ledger` semantics); CLI verb
  `python -m finance_engine.audit verify` → exit 0 / coded error on tamper.

- [ ] Red (sign-on-emit; `verify_integrity` passes; byte-tamper a line → fails coded) → green →
  `uv run poe gate` → commit → PR (human merge).

---

## Phase P6 — Wire Privacy-Core (Writ face, TS, repo `~/dev/oss/privacy-core`)

**Face:** Writ — the Egress Guard's `approve()` (mints the sendable `RedactedPayload`) is the
allow decision; seal it as a signed egress receipt. **Mode:** TS via `@edgeproc/avow`.
**Deploy:** npm (`@edgeproc/privacy-core` 0.2.0) — human-gated publish; `examples/demo` exercised
in CI. **Effort S/M. Risk:** keep the branded-type egress contract intact — receipts are
additive, never a bypass.

### Task P6.1: Egress receipts on approve/deny

**Files:**
- Create: `src/egressReceipt.ts`
- Modify: `src/egress.ts` (`approve()` optionally takes a `ReceiptSealer`; `guardedProvider`
  seals a deny receipt when `assertApproved` rejects), `src/index.ts` (export), `package.json`
  (dep `@edgeproc/avow`)
- Test: `src/egressReceipt.test.ts` + an addition to the e2e suite

**Interfaces:**
- Consumes: `PendingRedaction`, `RedactedPayload`, `assertApproved`; `@edgeproc/avow`
  `signPayload`/`contentHash`.
- Produces: `EgressSubject = {action: "llm.egress", provider: string, args_digest:
  contentHash({redactedText}), decision: "allow" | "deny", detector_version}`;
  `sealEgressReceipt(subject, seedHex): Promise<SignedReceipt<EgressSubject>>` — `args_digest`
  hashes the REDACTED text only; raw PII never enters a signed subject.

- [ ] Red (allow + deny paths; digest covers redacted-only; verify/tamper) → green → repo gates
  (vitest + playwright) → commit → PR (human merge).

---

## Phase P7 — Deploy, live-verify, publish (serial; mostly human-gated)

### Task P7.1: Merge train + CI green everywhere
- [ ] For each repo (avow, almamesh, aml-filter, edge-reco, personal-finances, privacy-core):
  PR open, gates green, **hand merge to Harish**, branch deleted after merge, main CI green
  (`gh run list` including scheduled security-audit).

### Task P7.2: Publish the Legos (HUMAN GATES)
- [ ] PyPI: `uv build && uv publish` for `avow` (Harish runs; trusted-publishing preferred).
- [ ] npm: `pnpm publish` for `@edgeproc/avow`; then `@edgeproc/privacy-core@0.2.0`.
- [ ] Tag per OSS convention: annotated SemVer at the CHANGELOG-matched commit; push tags.
- [ ] Post-publish: switch consumer dev path-deps (`[tool.uv.sources]`, pnpm links) to the
  published versions in a follow-up commit per repo.

### Task P7.3: Deploy + live end-to-end verification (the northstar closer)
- [ ] almamesh.com: after merge auto-deploys — drive the real site (browser MCP): open a domain
  strength view → receipt badge → download receipt → verify with published key → console clean.
- [ ] aml-filter.com: drive workstation → resolve a match → audit trail shows
  `RESOLUTION_SEALED` → receipt verifies against the Settings-page installation key → console
  clean.
- [ ] edge-reco.com: drive demo → "ranking weights verified" badge → tamper simulation test page
  path NOT deployed (verify-fail path covered by e2e only).
- [ ] personal-finances: local run — `sync` then `python -m finance_engine.audit verify` → OK;
  hand-tamper a line → coded failure.
- [ ] Record: portfolio.json status updates in `~/dev/project-ideas` (avow entry: shipped face
  status, proof links), regenerate views, commit `Portfolio: …`.
- [ ] Anything not drivable in the harness is listed explicitly as unverified in the closeout.

## Self-review notes (spec coverage)

- D1/D2/D3 answered with evidence (PyPI availability, Pyodide lock, existing noble/canonicalize
  precedent). Every consumer in the integration map has a phase; every phase names its exact
  seam file(s), mode, test, deploy target, effort, and human gates. Cross-language byte identity
  is enforced by P0.4 + P1.1/P1.2 vectors in CI, not asserted. The one intentional scope cut:
  Personal-Finances Writ-on-write-actions and Privacy-Core-as-Assay-input-sanitizer stay
  spec-future (read-only covenant / YAGNI), recorded in avow.md rather than built.
