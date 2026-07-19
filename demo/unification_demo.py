"""Unification demo: ONE signed-receipt envelope + ONE verifier serve BOTH faces.

The moat, made literal. Assay's *score* face signs "what a number is"; Writ's *effect*
face signs "what an effect did" and gates the effect behind a typed policy. This demo
produces one Assay score receipt and two Writ effect receipts (an allow and a deny),
then verifies ALL THREE with the SAME ``verify_receipt(..., expected_public_key=...)``
under ONE pinned signer key — proving the trust envelope is subject-agnostic.

Run it:  uv run python demo/unification_demo.py

Honest scope: the governed gate is the v0 capability-holding approximation — the
credential lives in-process, captured by the agent's gate closure (see ``assay.writ``).
Separate-process / WASM-guest enforcement is the v1 hardening."""

from __future__ import annotations

from collections.abc import Callable

from nacl.signing import SigningKey

from assay.api import score
from assay.canonical import content_hash
from assay.models import ScoreRequest
from assay.receipt import ScoreReceipt
from assay.settings import AssaySettings
from assay.verify import verify_receipt
from assay.writ import (
    Allowlist,
    EffectReceipt,
    EffectRequest,
    KeyholderEffector,
    governed_gate,
)

_SEED = bytes(range(32))
_ALLOWED = frozenset({"read"})

type AgentGate = Callable[[EffectRequest], EffectReceipt]


def _pubkey(key: SigningKey) -> str:
    """The signer's public key, pinned by the verifier out-of-band."""
    return bytes(key.verify_key).hex()


def _score_receipt(key: SigningKey) -> ScoreReceipt:
    request = ScoreRequest(
        metric="binary",
        metric_version="1",
        y_true=tuple([0, 1] * 20),
        y_score=tuple([0.2, 0.8] * 20),
    )
    return score(request, signing_key=key, settings=AssaySettings())


def _effect_request(action: str) -> EffectRequest:
    """An effect request; ``args_digest`` is a real content hash of the arguments, so
    the signed subject never carries the raw payload."""
    args_digest = content_hash({"resource": "ledger-7"})
    return EffectRequest(action=action, target="ledger-7", args_digest=args_digest)


def _build_agent_gate(key: SigningKey, performed: list[str]) -> AgentGate:
    """The trusted host wires the credential + privileged effect into an effector and
    hands the agent ONLY the bound gate. ``performed`` stands in for the real resource
    the effect mutates, so the demo can observe whether the effect actually ran."""

    def effect(request: EffectRequest) -> None:
        performed.append(request.action)

    effector = KeyholderEffector(effect=effect, signing_key=key)
    return governed_gate(Allowlist(_ALLOWED), effector)


def _run_allow(agent_gate: AgentGate, pub: str, performed: list[str]) -> EffectReceipt:
    receipt = agent_gate(_effect_request("read"))
    verify_receipt(receipt, expected_public_key=pub)
    assert receipt.payload.decision == "allow"
    assert performed == ["read"]  # the allowed effect actually ran
    print(f"[writ allow] '{receipt.payload.action}' ran -> signed allow receipt verified")
    return receipt


def _run_deny(agent_gate: AgentGate, pub: str, performed: list[str]) -> EffectReceipt:
    receipt = agent_gate(_effect_request("delete"))
    verify_receipt(receipt, expected_public_key=pub)
    assert receipt.payload.decision == "deny"
    assert performed == ["read"]  # unchanged: the denied effect never ran
    print(f"[writ deny]  '{receipt.payload.action}' blocked -> signed denial verified, no effect")
    return receipt


def _prove_unification(
    score_receipt: ScoreReceipt, allow: EffectReceipt, deny: EffectReceipt, pub: str
) -> None:
    """The SAME verify_receipt checks a score subject and two effect subjects."""
    verify_receipt(score_receipt, expected_public_key=pub)
    verify_receipt(allow, expected_public_key=pub)
    verify_receipt(deny, expected_public_key=pub)
    subjects = tuple(type(r.payload).__name__ for r in (score_receipt, allow, deny))
    print(f"[proof] one verify_receipt verified subjects {subjects} under one pinned key")


def main() -> int:
    """Prove one envelope + one verifier serve both faces; return 0 on success."""
    key = SigningKey(_SEED)
    pub = _pubkey(key)
    score_receipt = _score_receipt(key)
    verify_receipt(score_receipt, expected_public_key=pub)
    print(f"[score] Assay score={score_receipt.payload.score} -> signed receipt verified")
    performed: list[str] = []
    agent_gate = _build_agent_gate(key, performed)
    allow = _run_allow(agent_gate, pub, performed)
    deny = _run_deny(agent_gate, pub, performed)
    _prove_unification(score_receipt, allow, deny, pub)
    print("unification proven: one envelope + one verifier serve both the score and effect faces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
