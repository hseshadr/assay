"""Writ: the *effect* face of the shared trust envelope.

Where the score face (``assay``) signs *what a number is*, Writ signs *what an
effect did* — and gates the effect behind a typed policy. Both faces flow through the
SAME ``SignedReceipt`` envelope and the SAME ``sign_payload`` / ``verify_signature``
seam (see ``avow``): one envelope carries a score for one subject and an
effect for another, with zero changes to the trust boundary. That is the unification.

How the effect is governed:

* ``EffectSubject`` is Writ's signable subject — the effect-face analog of the score
  face's ``ReceiptPayload``.
* ``gate`` evaluates a typed ``Policy``. On **deny** it seals a signed ``not_run``
  receipt and never runs the effect. On **allow** it seals an ``attempted`` receipt and
  emits it BEFORE running the effect, then runs the effect and seals the ``succeeded`` /
  ``failed`` outcome — so a failed or partial privileged effect always leaves a signed
  attestation of the attempt, never a silent gap. Every sealed receipt flows to the
  optional ``emit`` sink; wire it to the ledger for durable, atomic attestation. All are
  verifiable through the shared envelope.
* ``KeyholderEffector`` is the sole holder of the effect credential (the signing key)
  *and* of the privileged effect. ``governed_gate`` binds policy + effector into the
  single closure the agent receives; the effector is captured, never passed, so the
  only path to the effect is back through the guard.

**Honest v0 caveat — not yet truly un-bypassable.** The credential lives in-process,
captured by the gate closure. Same-process reflection (walking ``__closure__``, etc.)
could still reach it, so this is a *capability-holding approximation*, not enforcement.
TRUE un-bypassability (a separate-process broker or a WASM guest, where the agent's
address space cannot reach the credential) is the v1 hardening. Do not overclaim.
The v0 policy decider is a Python predicate; OPA/Rego is the v1 decider.

**Honest v0 caveat — ``args_digest`` is asserted by the caller, not bound.** The gate
signs the digest it is handed and never recomputes it, because it never receives the
raw arguments. A caller that submits a digest of one thing and performs another still
gets a validly-signed receipt. So a receipt attests *"this signer claimed this action,
target and digest, and the policy decided this"* — not *"these are the arguments the
effect ran with"*. Binding it means the request carrying the real arguments and the
gate deriving the digest, which changes ``EffectRequest``'s public shape: a v1 change."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol

from nacl.signing import SigningKey
from pydantic import BaseModel, ConfigDict

from avow import SignedReceipt, sign_payload

type Decision = Literal["allow", "deny"]

# What became of the effect. ``not_run`` = denied (or an allowed effect never reached);
# ``attempted`` = sealed the instant before the effect ran; ``succeeded`` / ``failed`` =
# sealed after it returned or threw. Signed into the subject, so the outcome is attested.
type Outcome = Literal["not_run", "attempted", "succeeded", "failed"]


class EffectRequest(BaseModel):
    """What an agent asks the gate to perform. The credential to perform it is NOT
    here — it lives inside the effector the agent never receives.

    ``args_digest`` is the caller's *claim* about the arguments, kept as a hash so the
    signed subject never carries raw payloads. The gate signs that claim without
    checking it against anything (see this module's docstring): it is asserted, not
    bound."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str
    target: str
    args_digest: str


class EffectSubject(BaseModel):
    """Writ's deterministic, signable subject — the effect-face analog of the score
    face's ``ReceiptPayload``. The envelope signs it without inspecting its fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str
    target: str
    args_digest: str
    decision: Decision
    outcome: Outcome


# The effect face's concrete envelope: ``SignedReceipt`` parametrized with the effect
# subject, exactly as ``ScoreReceipt`` is ``SignedReceipt[ReceiptPayload]``.
EffectReceipt = SignedReceipt[EffectSubject]

# The privileged side-effect the gate guards. It runs ONLY on an allow decision.
type Effect = Callable[[EffectRequest], None]

# Where each sealed receipt is recorded as the gate produces it. The default drops them
# (return-only); wire it to durable storage (e.g. ``avow.ledger.append``) so the
# ``attempted`` receipt survives even when the effect later throws.
type Sink = Callable[[EffectReceipt], None]


def _noop(_: EffectReceipt) -> None:
    """Default sink: keep the return-only contract for callers that don't record."""


class Policy(Protocol):
    """A typed guard: may this request proceed? v0 is a Python predicate; the v1
    decider is OPA/Rego. The gate branches only on this boolean."""

    # A Protocol body is a structural-typing stub; it is never executed. Marked
    # explicitly rather than hidden by a broad coverage-exclusion regex.
    def permits(self, request: EffectRequest) -> bool: ...  # pragma: no cover


class Allowlist:
    """v0 policy: permit only allow-listed actions. (v1 decider: OPA/Rego.)"""

    def __init__(self, allowed_actions: frozenset[str]) -> None:
        self._allowed = allowed_actions

    def permits(self, request: EffectRequest) -> bool:
        return request.action in self._allowed


class Effector(Protocol):
    """Sole holder of the effect credential. Runs the effect and seals receipts with
    its held signing key. The agent never receives this object — only the bound gate."""

    # Protocol stubs; never executed (see Policy.permits).
    def run(self, request: EffectRequest) -> None: ...  # pragma: no cover

    def seal(self, subject: EffectSubject) -> EffectReceipt: ...  # pragma: no cover


class KeyholderEffector:
    """Concrete effector holding BOTH the privileged effect and the signing credential.

    Un-bypassable seam (honest v0): both live only here, captured by the gate closure;
    the agent gets the closure, never this object. v1 hardening: move behind a separate
    process / WASM guest so same-process reflection cannot reach the credential."""

    def __init__(self, effect: Effect, signing_key: SigningKey) -> None:
        self._effect = effect
        self._signing_key = signing_key

    def run(self, request: EffectRequest) -> None:
        self._effect(request)

    def seal(self, subject: EffectSubject) -> EffectReceipt:
        return sign_payload(subject, self._signing_key)


def _subject(request: EffectRequest, decision: Decision, outcome: Outcome) -> EffectSubject:
    return EffectSubject(
        action=request.action,
        target=request.target,
        args_digest=request.args_digest,
        decision=decision,
        outcome=outcome,
    )


def _seal(
    effector: Effector,
    request: EffectRequest,
    decision: Decision,
    outcome: Outcome,
    emit: Sink,
) -> EffectReceipt:
    """Seal one outcome receipt and hand it to the sink before returning it."""
    receipt = effector.seal(_subject(request, decision, outcome))
    emit(receipt)
    return receipt


def _run_and_seal(request: EffectRequest, effector: Effector, emit: Sink) -> EffectReceipt:
    """Run an allowed effect and seal its outcome; on a throw, seal ``failed`` then
    re-raise so the failure is both attested and never silently swallowed."""
    try:
        effector.run(request)
    except Exception:
        _seal(effector, request, "allow", "failed", emit)
        raise
    return _seal(effector, request, "allow", "succeeded", emit)


def gate(
    request: EffectRequest, policy: Policy, effector: Effector, *, emit: Sink = _noop
) -> EffectReceipt:
    """Govern one effect atomically. On deny, seal a ``not_run`` receipt. On allow, seal
    an ``attempted`` receipt and emit it BEFORE running the effect, then run and seal the
    ``succeeded`` / ``failed`` outcome — so a failed or partial effect still leaves a
    signed attestation. Each sealed receipt flows to ``emit`` (wire it to the ledger for
    durable capture); all are verifiable via the shared envelope."""
    if not policy.permits(request):
        return _seal(effector, request, "deny", "not_run", emit)
    _seal(effector, request, "allow", "attempted", emit)
    return _run_and_seal(request, effector, emit)


def governed_gate(
    policy: Policy, effector: Effector, *, emit: Sink = _noop
) -> Callable[[EffectRequest], EffectReceipt]:
    """Bind policy + effector into the ONLY handle the agent receives. The effector
    (holding the credential and the effect) is captured, never exposed, so the sole
    path to the effect is back through this guard. ``emit`` is threaded to ``gate`` so
    the bound handle records its attestations durably too."""

    def bound(request: EffectRequest) -> EffectReceipt:
        return gate(request, policy, effector, emit=emit)

    return bound
