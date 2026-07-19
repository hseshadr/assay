from __future__ import annotations

import pytest
from nacl.signing import SigningKey
from pydantic import ValidationError

from avow import SignedReceipt, payload_digest, verify_signature
from avow.errors import SignatureInvalid
from writ import (
    Allowlist,
    Effect,
    EffectReceipt,
    EffectRequest,
    EffectSubject,
    KeyholderEffector,
    gate,
    governed_gate,
)

_SEED = bytes(range(32))
_EXPECTED = bytes(SigningKey(_SEED).verify_key).hex()


def _request(action: str = "read") -> EffectRequest:
    return EffectRequest(action=action, target="account-7", args_digest="sha256:abc")


def _recorder() -> tuple[list[EffectRequest], Effect]:
    """A privileged effect that records what it performed, so tests can assert whether
    the side-effect actually happened."""
    log: list[EffectRequest] = []

    def effect(request: EffectRequest) -> None:
        log.append(request)

    return log, effect


def _effector(effect: Effect) -> KeyholderEffector:
    return KeyholderEffector(effect=effect, signing_key=SigningKey(_SEED))


def test_should_reject_a_decision_that_is_not_allow_or_deny() -> None:
    # Given a subject built with an out-of-vocabulary decision
    # Then the Literal["allow","deny"] contract rejects it at the boundary
    with pytest.raises(ValidationError):
        EffectSubject(action="read", target="t", args_digest="sha256:abc", decision="maybe")  # type: ignore[arg-type]


def test_should_allowlist_permit_listed_actions_and_deny_others() -> None:
    # Given a policy that allow-lists only "read"
    policy = Allowlist(frozenset({"read"}))
    # Then a listed action passes and any other is denied
    assert policy.permits(_request("read")) is True
    assert policy.permits(_request("delete")) is False


def test_should_perform_effect_and_seal_a_verifiable_allow_receipt() -> None:
    # Given a gate whose policy permits the requested action
    log, effect = _recorder()
    receipt = gate(_request("read"), Allowlist(frozenset({"read"})), _effector(effect))
    # Then the effect actually ran, and a signed allow receipt verifies under the pinned key
    assert log == [_request("read")]
    assert receipt.payload.decision == "allow"
    assert isinstance(receipt, SignedReceipt)
    verify_signature(receipt, expected_public_key=_EXPECTED)


def test_should_skip_effect_and_seal_a_verifiable_deny_receipt() -> None:
    # Given a gate whose policy denies the requested action
    log, effect = _recorder()
    receipt = gate(_request("delete"), Allowlist(frozenset({"read"})), _effector(effect))
    # Then NO effect ran, yet a signed denial receipt still verifies under the pinned key
    assert log == []
    assert receipt.payload.decision == "deny"
    verify_signature(receipt, expected_public_key=_EXPECTED)


def test_should_carry_the_effect_subject_verbatim_in_the_sealed_receipt() -> None:
    # Given a sealed allow receipt
    _, effect = _recorder()
    request = _request("read")
    receipt = gate(request, Allowlist(frozenset({"read"})), _effector(effect))
    # Then the envelope carries the subject unchanged and hashes it with the shared digest
    assert receipt.payload.action == request.action
    assert receipt.payload.target == request.target
    assert receipt.payload.args_digest == request.args_digest
    assert receipt.payload_hash == payload_digest(receipt.payload)


def test_should_reject_a_writ_receipt_under_a_different_pinned_key() -> None:
    # Given a genuine effect receipt
    _, effect = _recorder()
    receipt = gate(_request("read"), Allowlist(frozenset({"read"})), _effector(effect))
    # Then pinning a different signer rejects it — authenticity is pinned, not embedded
    with pytest.raises(SignatureInvalid):
        verify_signature(receipt, expected_public_key="ab" * 32)


def test_should_seal_with_the_held_credential_only() -> None:
    # Given a keyholder effector sealing a subject directly
    _, effect = _recorder()
    subject = EffectSubject(action="read", target="t", args_digest="sha256:abc", decision="allow")
    receipt: EffectReceipt = _effector(effect).seal(subject)
    # Then the receipt is signed by the effector's held key (its embedded pubkey matches)
    assert receipt.public_key == _EXPECTED
    verify_signature(receipt, expected_public_key=_EXPECTED)


def test_should_hand_the_agent_only_a_gate_that_hides_the_credential() -> None:
    # Given the bound gate an agent receives from governed_gate
    log, effect = _recorder()
    agent_gate = governed_gate(Allowlist(frozenset({"read"})), _effector(effect))
    # Then the handle exposes neither the effect nor the sealing credential surface
    assert callable(agent_gate)
    assert not hasattr(agent_gate, "run")
    assert not hasattr(agent_gate, "seal")
    # And it still governs: allow performs + verifies, deny skips + verifies
    allow = agent_gate(_request("read"))
    deny = agent_gate(_request("delete"))
    assert allow.payload.decision == "allow"
    assert deny.payload.decision == "deny"
    assert log == [_request("read")]  # only the allowed effect ever ran
    verify_signature(allow, expected_public_key=_EXPECTED)
    verify_signature(deny, expected_public_key=_EXPECTED)
