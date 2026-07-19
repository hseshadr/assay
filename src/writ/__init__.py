"""Writ: the effect face of the Avow envelope — sign *what an effect did*, gated.

Writ supplies its own signable subject (``EffectSubject``) and reuses the shared
``avow`` envelope unchanged: one envelope, one verifier, two faces. It depends only on
``avow`` (no heavy extras)."""

from __future__ import annotations

from writ.gate import (
    Allowlist,
    Decision,
    Effect,
    Effector,
    EffectReceipt,
    EffectRequest,
    EffectSubject,
    KeyholderEffector,
    Policy,
    gate,
    governed_gate,
)

__all__ = [
    "Allowlist",
    "Decision",
    "Effect",
    "EffectReceipt",
    "EffectRequest",
    "EffectSubject",
    "Effector",
    "KeyholderEffector",
    "Policy",
    "gate",
    "governed_gate",
]
