"""Writ: the *effect* face of the shared trust envelope.

Where the score face (``assay``) signs *what a number is*, Writ signs *what an
effect did* — and gates the effect behind a typed policy. Both faces flow through the
SAME ``SignedReceipt`` envelope and the SAME ``sign_payload`` / ``verify_signature``
seam (see ``avow``): one envelope carries a score for one subject and an
effect for another, with zero changes to the trust boundary. That is the unification.

Governed effect (moat, stated honestly):

* ``EffectSubject`` is Writ's signable subject — the effect-face analog of the score
  face's ``ReceiptPayload``.
* ``gate`` evaluates a typed ``Policy``. On **deny** it seals a signed denial receipt
  and never runs the effect; on **allow** the effector runs the effect, then seals a
  signed effect receipt. Both outcomes are verifiable through the shared envelope.
* ``KeyholderEffector`` is the sole holder of the effect credential (the signing key)
  *and* of the privileged effect. ``governed_gate`` binds policy + effector into the
  single closure the agent receives; the effector is captured, never passed, so the
  only path to the effect is back through the guard.

**Honest v0 caveat — not yet truly un-bypassable.** The credential lives in-process,
captured by the gate closure. Same-process reflection (walking ``__closure__``, etc.)
could still reach it, so this is a *capability-holding approximation*, not enforcement.
TRUE un-bypassability (a separate-process broker or a WASM guest, where the agent's
address space cannot reach the credential) is the v1 hardening. Do not overclaim.
The v0 policy decider is a Python predicate; OPA/Rego is the v1 decider."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol

from nacl.signing import SigningKey
from pydantic import BaseModel, ConfigDict

from avow import SignedReceipt, sign_payload

type Decision = Literal["allow", "deny"]


class EffectRequest(BaseModel):
    """What an agent asks the gate to perform. The credential to perform it is NOT
    here — it lives inside the effector the agent never receives. ``args_digest`` is
    a content hash of the real arguments, so the signed subject never carries raw
    payloads."""

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


# The effect face's concrete envelope: ``SignedReceipt`` parametrized with the effect
# subject, exactly as ``ScoreReceipt`` is ``SignedReceipt[ReceiptPayload]``.
EffectReceipt = SignedReceipt[EffectSubject]

# The privileged side-effect the gate guards. It runs ONLY on an allow decision.
type Effect = Callable[[EffectRequest], None]


class Policy(Protocol):
    """A typed guard: may this request proceed? v0 is a Python predicate; the v1
    decider is OPA/Rego. The gate branches only on this boolean."""

    def permits(self, request: EffectRequest) -> bool: ...


class Allowlist:
    """v0 policy: permit only allow-listed actions. (v1 decider: OPA/Rego.)"""

    def __init__(self, allowed_actions: frozenset[str]) -> None:
        self._allowed = allowed_actions

    def permits(self, request: EffectRequest) -> bool:
        return request.action in self._allowed


class Effector(Protocol):
    """Sole holder of the effect credential. Runs the effect and seals receipts with
    its held signing key. The agent never receives this object — only the bound gate."""

    def run(self, request: EffectRequest) -> None: ...

    def seal(self, subject: EffectSubject) -> EffectReceipt: ...


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


def _subject(request: EffectRequest, decision: Decision) -> EffectSubject:
    return EffectSubject(
        action=request.action,
        target=request.target,
        args_digest=request.args_digest,
        decision=decision,
    )


def gate(request: EffectRequest, policy: Policy, effector: Effector) -> EffectReceipt:
    """Govern one effect: evaluate the policy, run the effect ONLY on allow, and seal
    a signed, verifiable receipt for BOTH outcomes via the shared envelope."""
    decision: Decision = "allow" if policy.permits(request) else "deny"
    if decision == "allow":
        effector.run(request)
    return effector.seal(_subject(request, decision))


def governed_gate(policy: Policy, effector: Effector) -> Callable[[EffectRequest], EffectReceipt]:
    """Bind policy + effector into the ONLY handle the agent receives. The effector
    (holding the credential and the effect) is captured, never exposed, so the sole
    path to the effect is back through this guard."""

    def bound(request: EffectRequest) -> EffectReceipt:
        return gate(request, policy, effector)

    return bound
