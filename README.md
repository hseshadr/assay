# avow

**Proof of what your software decided — a receipt that is tamper-evident: edit it and it stops verifying.**

---

Your card gets declined at a checkout.

You call the bank and ask why. Someone reads a reason off a screen: the fraud system
scored the transaction as risky, so it blocked it.

But that reason is just a row in a database. Rows can be changed. Nobody — not you, not
the bank's own auditor, not a regulator — can tell whether that number is what the
software actually produced at the moment it blocked your card, or whether somebody
adjusted it afterwards, once you complained.

That is the gap `avow` closes.

## What it does

When your software makes a decision, avow has it write a **receipt**: a small record of
exactly what was decided, sealed with cryptography at the moment of the decision.

Think of a store receipt — except this one cannot be reprinted or altered. You can hand
it to anyone. They can check it on their own laptop, offline, with no access to your
database, and get one of two answers:

- **valid** — this is exactly what the software decided, byte for byte
- **invalid** — someone changed it

There is no "close enough". Change one digit anywhere in it and the check fails.

## Before you install

Two things that will otherwise trip you up:

- **Python 3.13 or newer is required.** On 3.12 or older `pip install avow` fails while
  resolving, with a message that does not mention the Python version. Check with
  `python --version` first.
- **The package is `avow`; the command is `assay`.** You `pip install avow` and
  `import avow`, but the command line the CLI extra installs is called `assay`. There is
  no `avow` command. (`avow` is the envelope everything is built on; `assay` is the
  scoring face that ships the CLI.)

## See it catch a tampered record

```bash
python --version   # must be 3.13+
pip install avow
```

```python
from pydantic import BaseModel, ConfigDict

from avow import generate_signing_key, public_key_hex, sign_payload, verify_signature


class FraudCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    transaction_id: str
    decision: str
    risk_score: float
    model_version: str


key = generate_signing_key()        # the bank's private signing key
trusted_key = public_key_hex(key)   # published once; this is what checkers pin

receipt = sign_payload(
    FraudCheck(
        transaction_id="txn-9471",
        decision="blocked",
        risk_score=0.83,
        model_version="fraud-v4",
    ),
    key,
)

verify_signature(receipt, expected_public_key=trusted_key)
print("original receipt ..... VALID")

# Someone edits the stored record to make the block look better justified.
tampered = receipt.model_copy(
    update={"payload": receipt.payload.model_copy(update={"risk_score": 0.99})}
)

try:
    verify_signature(tampered, expected_public_key=trusted_key)
    print("edited receipt ....... VALID  <- this must never happen")
except Exception as exc:
    print(f"edited receipt ....... REJECTED ({type(exc).__name__})")
```

```
original receipt ..... VALID
edited receipt ....... REJECTED (ReplayMismatch)
```

Nudging `0.83` to `0.99` — a change that would be invisible in a database — makes the
receipt fail to verify. That is the whole idea.

## What a receipt proves, and what it does not

This is the part most signing libraries gloss over, so read it before you rely on avow.

A receipt proves **integrity**: the contents have not changed since they were signed.

It does **not**, on its own, prove **authenticity** — that *your* system is the one that
signed it.

Here is why, concretely. The signer's public key travels inside the receipt, but
*outside* the portion that is actually signed. So an attacker can write any payload they
like, sign it with a key they generated themselves, and drop their own public key into
the receipt. That forgery is internally consistent: its hash and its signature agree with
each other perfectly.

The only thing that stops it is **pinning** — deciding in advance which public key you
trust, obtaining it through a separate channel (the `.pub` file from `keygen`, your
config, your secret manager), and passing that key to the verifier:

```python
from pydantic import BaseModel, ConfigDict

from avow import generate_signing_key, public_key_hex, sign_payload, verify_signature


class FraudCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    transaction_id: str
    decision: str
    risk_score: float
    model_version: str


bank = generate_signing_key()
trusted_key = public_key_hex(bank)      # what you pin, out-of-band

attacker = generate_signing_key()       # a key anyone can make in one line
forged = sign_payload(
    FraudCheck(
        transaction_id="txn-9471",
        decision="approved",            # a total fabrication
        risk_score=0.01,
        model_version="fraud-v4",
    ),
    attacker,
)

# The forgery is internally consistent: its hash and signature agree with each other.
print(f"forged receipt is self-consistent: {forged.payload_hash[:16]}... signed OK by attacker")

try:
    verify_signature(forged, expected_public_key=trusted_key)
    print("forged receipt ....... VALID  <- this must never happen")
except Exception as exc:
    print(f"forged receipt ....... REJECTED ({type(exc).__name__}: {exc.code})")

# The ONLY reason it was rejected is that we pinned the bank's key.
print(f"key inside forgery matches bank? {forged.public_key == trusted_key}")
```

```
forged receipt is self-consistent: sha256:441280ee2... signed OK by attacker
forged receipt ....... REJECTED (SignerMismatch: avow.signer_mismatch)
key inside forgery matches bank? False
```

**Never trust the key embedded in the receipt.** It rides along for convenience; it is
not the trust anchor. `verify_signature` *requires* you to pass the key you already
trust, precisely so this mistake is hard to make by accident.

Note the code: **`avow.signer_mismatch`**, not `avow.signature_invalid`. Those are two
different events and they are coded apart, because you may want to react differently:

| Code | Class | What happened |
|---|---|---|
| `avow.signer_mismatch` | `SignerMismatch` | Signed by a key you do not trust — a **provenance** failure. The signature is never even checked. |
| `avow.signature_invalid` | `SignatureBytesInvalid` | The signer matched, but the bytes fail the curve check — a **tamper** failure. |

Both subclass `SignatureInvalid`, so `except SignatureInvalid:` still catches either one
if you do not care which. You never have to match on the message text.

## Three things you can sign

Avow ships as one installable package with three importable pieces. The first is the
core; the other two are ready-made shapes built on it.

### 1. Anything — `avow`, the envelope

Shown above. You define what a decision looks like, avow seals and checks it. It never
looks inside your data, so the same sign-and-verify code works for any record.

### 2. A measurement that refuses to overstate — `assay`

A number like "our model is 89% accurate" is only meaningful if enough examples stood
behind it. Measure 12 cases and you can get any number you like; it is noise.

`assay` computes the score **and** its error bar, and when the sample is too thin it
returns nothing at all rather than inventing a figure. Both outcomes come back inside a
signed receipt.

```bash
pip install 'avow[assay]'
```

```python
import random

from assay import score, verify
from assay.models import ScoreRequest
from assay.settings import AssaySettings
from avow import generate_signing_key, public_key_hex

key = generate_signing_key()
settings = AssaySettings()  # sample-size floor: 30


def evaluate(label: str, n: int) -> None:
    rng = random.Random(7)
    # a fraud model that is good, not perfect
    y_true = tuple(int(rng.random() < 0.3) for _ in range(n))
    y_score = tuple(min(1.0, max(0.0, rng.gauss(0.75 if t else 0.25, 0.22))) for t in y_true)

    receipt = score(
        ScoreRequest(metric="binary", metric_version="1", y_true=y_true, y_score=y_score),
        signing_key=key,
        settings=settings,
    )
    assert verify(receipt, expected_public_key=public_key_hex(key))

    r = receipt.payload
    if r.abstained:
        print(f"{label:<10} n={n:<4} accuracy = (none) -- {r.abstain_reason}")
    else:
        print(
            f"{label:<10} n={n:<4} accuracy = {r.score:.2f}  "
            f"95% interval [{r.interval_low:.2f}, {r.interval_high:.2f}]"
        )


evaluate("pilot", 12)
evaluate("full eval", 400)
```

```
pilot      n=12   accuracy = (none) -- assay.insufficient_samples
full eval  n=400  accuracy = 0.89  95% interval [0.86, 0.92]
```

The pilot run declines to produce a number. The full run reports 0.89 *and* admits the
true value is somewhere in [0.86, 0.92]. The receipt also carries precision, recall, F1,
PR-AUC, ROC-AUC, and a calibration report — see the reference section.

### 3. An action that was actually allowed — `writ`

Before your code does something irreversible — delete a record, move money, send an email
— `writ` checks a policy. If the policy says no, the action never runs. Either way you
get a signed receipt of what was asked and what was decided, so "the agent deleted it"
and "we blocked the agent" are both provable after the fact.

This matters most when the caller is an AI agent you do not fully control.

```python
from avow import content_hash, generate_signing_key, public_key_hex, verify_signature
from writ import Allowlist, EffectRequest, KeyholderEffector, governed_gate

key = generate_signing_key()
performed: list[str] = []  # stands in for the real system being changed


def perform(request: EffectRequest) -> None:
    """The privileged action. Reached ONLY through an allow decision."""
    performed.append(f"{request.action} {request.target}")


# The trusted host wires policy + action + key into the gate, then hands the agent
# exactly one thing: the gate. The agent never receives the key or the action itself.
agent_gate = governed_gate(
    Allowlist(frozenset({"read"})),
    KeyholderEffector(effect=perform, signing_key=key),
)

for action in ("read", "delete"):
    receipt = agent_gate(
        EffectRequest(
            action=action,
            target="customer-4471",
            args_digest=content_hash({"reason": "agent cleanup task"}),
        )
    )
    verify_signature(receipt, expected_public_key=public_key_hex(key))
    print(f"agent asked to {action:<6} -> {receipt.payload.decision:<5} (signed receipt verified)")

print(f"actually performed: {performed}")
```

```
agent asked to read   -> allow (signed receipt verified)
agent asked to delete -> deny  (signed receipt verified)
actually performed: ['read customer-4471']
```

The denied delete produced a signed receipt but never touched the system.

## Command line

For signing and checking receipts without writing code. The distribution is `avow`; the
command it installs is **`assay`** (there is no `avow` command). Python 3.13+ required.

```bash
pip install 'avow[cli]'                        # installs the `assay` command

assay --help                                   # note: `assay`, not `avow`
assay keygen --out signing.key                 # also writes signing.key.pub
echo '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}' > req.json
assay score --request req.json --key signing.key --out receipt.json --ledger ledger.jsonl
assay verify --receipt receipt.json --public-key signing.key.pub
```

```
wrote signing key: signing.key
wrote public key: signing.key.pub
wrote receipt: receipt.json
OK: receipt verified
```

### Auditing the ledger — `verify-ledger`

> The signature-verifying `verify-ledger` lands in `avow` 0.2.0 (this repo). The
> published 0.1.x shipped an earlier hash-only audit — upgrade for real tamper-evidence.
> Install with `pip install 'avow[cli]'` (Python 3.13+; use a fresh venv) and run
> `assay verify-ledger --help`.

`score` also appended that receipt to `ledger.jsonl`. A ledger is checkable on its own,
using the signer's **public** key — never the secret signing key. A content hash alone
is not enough: an adversary who edits an entry can recompute its (public) hash, so
tamper-evidence rests on the Ed25519 signature, which only the private seed can produce.
Anyone holding the file and the public key can audit it:

```bash
assay verify-ledger --ledger ledger.jsonl --public-key signing.key.pub
```

```
OK: ledger verified, 1 entry intact
```

Four samples is below the abstention floor, so that receipt honestly records
`"abstained":true` and no score. Now edit the stored entry to claim a confident answer
it never gave — change `"abstained":true` to `"abstained":false`, the sort of quiet
correction that leaves no trace in an ordinary log — and ask again:

```bash
assay verify-ledger --ledger ledger.jsonl --public-key signing.key.pub
```

```
FAIL: avow.ledger_integrity: tampered ledger entry: sha256:a2ada15199d7586958d9754a4adeba4d13a4e73122f9604f65a536fb4a4bad7e
```

Exit code `1`, and the coded cause names both the failure and the entry that caused it.
The check re-derives every entry's hash **and** verifies its signature under the pinned
key, failing closed on the first disagreement.

A ledger it cannot read is also a failure, not a pass. Mistype the path and you get:

```
FAIL: avow.ledger_unreadable: ledger is not a readable file: ledgr.jsonl
```

rather than `OK: ledger verified, 0 entries intact` — which would be a clean bill of
health for a file that was never opened. The same applies to a directory in the file's
place, a file whose permissions deny reading, and a line that is not a parseable receipt
(`avow.ledger_entry_malformed`). A ledger that *exists and is empty* still passes with
zero entries.

> **What this check does not cover.** It verifies each entry it is shown — not the *set*
> of entries. Deleting, truncating, reordering, replaying, or splicing in whole entries is
> **not detected**, including a ledger emptied outright, which is why the zero-entry pass
> above is not evidence that nothing was removed. Read
> [Honest limits](#honest-limits) before you rely on this file as a history.

## Honest limits

Stated plainly, because each of these is a real boundary on what avow currently gives you.

- **A receipt proves integrity, not authenticity, unless you pin the key.** See the
  section above. This is the single easiest way to misuse the library.
- **The ledger is not append-only in the tamper-evident sense.** It detects tampering
  *within* an entry; it does not detect tampering *with the set of entries*.
  `verify_integrity` walks the lines it is handed and re-derives each one's hash and
  Ed25519 signature. That proves *"every line I was shown is genuine"*. It does not prove
  *"these are the lines, in this order, and all of them"*, because nothing links one entry
  to the next — no `prev_hash`, no sequence number, no root. Concretely, every one of the
  following returns `OK: ledger verified, N entries intact` and exit code `0` today:
  **deleting** an entry from the middle, **truncating** the file (including emptying it
  completely), **reordering** entries, **replaying** a genuine entry a second time, and
  **splicing in** a genuine entry from a different ledger signed by the same key. An
  emptied ledger is byte-identical to a fresh one, so nothing in the file can tell them
  apart. Do not read a passing audit as proof that a history is complete, ordered, or
  unaltered — read it as proof that the entries *you still have* were not individually
  edited. The fix is a hash chain (`prev_hash` + sequence number, with the head pinned
  out-of-band, exactly as the pinned public key already is); it is **not** in this
  release. The five attacks above are encoded as strict-`xfail` tests in
  `tests/test_ledger.py`, so the suite goes red the day the chain lands and this
  disclosure goes stale.
- **`writ`'s enforcement is in-process (v0).** The signing key and the privileged action
  live only inside the effector, which the gate captures in a closure; the agent receives
  the closure and never the effector, so the only route to the action is through the
  guard. But the credential is still in the same process, so same-process reflection
  (walking `__closure__`, for instance) could reach it. This is a capability-holding
  *approximation*, not true enforcement. Real un-bypassability — a separate-process
  broker or a WASM guest, where the caller's address space cannot reach the credential —
  is the v1 hardening. We claim no more than that.
- **The v0 policy decider is a plain Python predicate** (`Allowlist`). OPA/Rego is the v1
  decider.
- **`writ` signs the `args_digest` its caller hands it; it does not recompute it.** The
  gate never sees the raw arguments, so it cannot check that the digest actually
  describes them. A caller that passes a digest of one thing and performs another gets a
  validly-signed receipt attesting the wrong arguments. What the receipt therefore
  proves is "this signer claimed this action, target and digest, and the policy decided
  this" — not "these are the arguments the effect ran with". Closing the gap means the
  request carrying the real arguments and the gate deriving the digest itself; that
  changes `EffectRequest`'s public shape, so it is a v1 change, not a patch.
- **Browser key custody is same-origin, not hardware-backed.** In the browser build, keys
  are protected by the origin boundary alone — there is no secure element or OS keychain
  behind them.
- **Receipts carry no timestamp.** That is deliberate: it makes them reproducible (the
  same inputs always yield the same receipt). It also means a receipt cannot tell you
  *when* it was made. If you need that, record it outside the receipt, in something you
  trust. **This bullet used to say "or append to the ledger"; we retract that.** Ledger
  position is not evidence of sequence — entries are independently signed and unlinked,
  so an entry can be moved, removed, or duplicated without the audit noticing (see the
  ledger bullet above). Until the chain lands, use a real timestamping service or an
  append-only store you already trust for ordering.

## Reference

<details>
<summary><b>Packages and install matrix</b></summary>

One distribution, `avow`, exposes three import packages:

| Package | What it is | Depends on | Install |
|---|---|---|---|
| **`avow`** | the shared **envelope** — sign, hash, verify a receipt | pydantic, pynacl, rfc8785 | `pip install avow` |
| **`assay`** | the **measurement** face — an honest number in a receipt | `avow` + scikit-learn/scipy/numpy | `pip install 'avow[assay]'` |
| **`writ`** | the **action** face — a policy-gated effect, sealed as a receipt | `avow` only | `pip install avow` |

Dependency arrows only ever point **into** `avow`: `assay → avow` and `writ → avow`.
Avow imports neither, which is why installing the envelope alone never pulls in the heavy
scientific stack. Importing `assay` without the `[assay]` extra raises a coded
`ScoringExtraMissing`, not a raw `ModuleNotFoundError`.

</details>

<details>
<summary><b>How the sealing works</b></summary>

Some terms, each in one line:

- **Content hash** — a short fingerprint of some data. Change any byte and the
  fingerprint changes completely. Avow uses SHA-256.
- **Canonicalization (RFC 8785 / JCS)** — one fixed way to write a JSON object as bytes,
  so that the same data always produces the same bytes regardless of key order or
  language. Without it, two systems could hash "the same" record differently.
- **Ed25519** — a signature scheme. A private key signs; the matching public key checks.
  Signing is deterministic: the same message and key always give the same signature.
- **Frozen subject** — the record being signed, declared immutable so it cannot be
  modified after signing.

`sign_payload` / `verify_signature` / `payload_digest` operate only on the canonical JSON
of a frozen subject, and never inspect its fields. That is why the same envelope carries a
measurement for `assay` and an action for `writ` with no change to the trust boundary.

Because payloads carry no timestamp, identical inputs yield an identical, reproducible,
offline-verifiable receipt.

`avow.ledger` is a content-addressed JSONL log of independently signed entries, generic
over the subject. Its audit fails closed **per entry** — re-deriving that entry's hash
**and** verifying its Ed25519 signature against a pinned public key. Entries are not
chained to one another, so the log is *append-only by construction* (writes are `O_APPEND`
under a lock) but **not append-only in the tamper-evident sense**: nothing detects a
removed, reordered, replayed, or spliced-in entry. See [Honest limits](#honest-limits).
Coded failures live in `avow.errors` (`avow.*` codes under `AvowError`).

</details>

<details>
<summary><b>Inside <code>assay</code></b></summary>

A thin trust, honesty, and composition layer over reused libraries — it computes no
metric math itself:

- scikit-learn for precision, recall, F1, PR-AUC, ROC-AUC and Brier score
- `scipy.stats.bootstrap` for percentile intervals, with a **sample-size floor**; below
  it, assay abstains rather than invent a point estimate
- population-weighted **ECE** (expected calibration error) for calibration
- a positive-weighted composite with a propagated interval

`assay.receipt` defines the measurement subjects; the envelope signs them. Errors are
`assay.*` under `AssayError`. Every tunable — the sample floor, resample count,
confidence level, bin count — lives in `AssaySettings` and is overridable via `ASSAY_*`
environment variables.

</details>

<details>
<summary><b>Inside <code>writ</code></b></summary>

`writ.gate(request, policy, effector, *, emit=...)` evaluates a typed policy. On **deny**
it seals a signed `not_run` receipt and never runs the effect. On **allow** it seals an
`attempted` receipt and hands it to `emit` **before** running the effect, then runs it and
seals the `succeeded` / `failed` outcome — so a failed or partial privileged effect always
leaves a signed attestation of the attempt. Wire `emit` to `avow.ledger.append` for
durable, atomic capture; every sealed receipt is verifiable through the shared envelope.

`EffectRequest.args_digest` is a hash rather than the arguments themselves, so the signed
record never carries raw payloads. It is the caller's claim about those arguments: the
gate signs it without recomputing it.

See the honest limits above for exactly how far the enforcement seam and that digest go in v0.

</details>

<details>
<summary><b>Key custody and cross-language vectors</b></summary>

`assay keygen` (and `avow.keys`) write a 32-byte Ed25519 seed to a `0600` file and the
public key to a companion `.pub`. Keys are never logged and never committed (`*.key` is
gitignored). The public key also travels inside each receipt for convenience, but that
embedded copy is **not** the trust anchor — a verifier pins the out-of-band key and passes
it to `verify`.

`testdata/vectors/` holds golden vectors generated by `tests/gen_vectors.py` (canonical
bytes and hashes, plus receipts signed with a fixed non-secret test seed). The Python
suite replays them in `tests/test_vectors.py`; the TypeScript `@edgeproc/avow` replays the
*same files* byte for byte, so any RFC 8785 number-serialization divergence fails in CI
rather than in production.

`@edgeproc/receipt-ui` (in `ts/packages/receipt-ui`) is the browser rendering layer: small,
fail-closed React components that verify a receipt against a pinned key and show the
verdict, built on the TypeScript `@edgeproc/avow` envelope above.

</details>

<details>
<summary><b>Working on avow itself</b></summary>

```bash
git clone https://github.com/hseshadr/assay.git && cd assay
uv sync --all-extras
uv run poe gate                          # Python: ruff, ruff-format, mypy --strict, xenon A, pytest
uv run poe gate-ts                       # TypeScript: biome, tsc --noEmit, vitest, build (needs pnpm)
uv run poe gate-all                      # both, mirroring CI's two jobs
uv run python demo/run_demo.py           # measurement face: 6 honesty acceptance cases
uv run python demo/unification_demo.py   # one envelope + one verifier, both faces
```

[`QUICKSTART.md`](QUICKSTART.md) is the shortest path from clone to a verified receipt.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the data-flow diagram, the import
edges, and the native-vs-browser story.

</details>

## Status

v0, deterministic — no LLM anywhere in the path.

Two gates, mirroring CI's two jobs. `uv run poe gate` covers **Python only** (ruff,
ruff-format, mypy `--strict`, xenon A, pytest with statement *and* branch coverage
against a floor); `uv run poe gate-ts` covers the TypeScript package (biome, `tsc`
strict, vitest, build). `uv run poe gate-all` runs both.

Published releases: `avow` 0.1.1 on PyPI and `@edgeproc/avow` 0.1.1 on npm (0.2.0 prepared
in this repo, not yet released); `@edgeproc/receipt-ui` 0.1.0 on npm (0.2.0, adding the
injectable `labels` i18n prop, prepared in this repo, not yet released) — see
[`CHANGELOG.md`](CHANGELOG.md) and
[`ts/packages/receipt-ui/CHANGELOG.md`](ts/packages/receipt-ui/CHANGELOG.md) for what each
release contains. Read the honest limits above before depending on any of it.

## License

MIT © Harish Seshadri
