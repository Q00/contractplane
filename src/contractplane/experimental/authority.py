"""Deny-by-default pre-dispatch authority gate.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

The gate turns a compiled stage's declared authority (its capability
``sideEffects`` class) into an allow/deny decision *before* any work is
dispatched. Nothing is permitted unless it was explicitly granted: a capability
that declares ``external`` side effects is denied unless the run was handed an
explicit external grant. The gate itself performs no side effects and never
touches the kernel; the harness feeds its decision into the kernel's existing
pre-dispatch ``authorization.decided`` transition, so every denial is recorded
in the append-only ledger exactly like a human refusal.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..compiler import CompiledStage

ACTOR = "authority-gate"


@dataclass(frozen=True)
class AuthorityGrant:
    """Explicit authority handed to a governed run. Absent grants mean deny.

    ``allow_local`` is on by default because a run always owns its confined
    workspace; ``allow_external`` is off by default because reaching outside the
    workspace is the boundary this gate exists to guard.
    """

    allow_local: bool = True
    allow_external: bool = False


@dataclass(frozen=True)
class AuthorityDecision:
    allowed: bool
    actor: str
    reason: str
    side_effects: str

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "actor": self.actor,
            "reason": self.reason,
            "sideEffects": self.side_effects,
        }


class AuthorityGate:
    """Decide, per stage, whether declared authority permits dispatch."""

    def __init__(self, grant: AuthorityGrant | None = None):
        self._grant = grant or AuthorityGrant()

    def decide(self, stage: CompiledStage) -> AuthorityDecision:
        side_effects = stage.side_effects
        if side_effects == "none":
            return AuthorityDecision(
                allowed=True,
                actor=ACTOR,
                reason="capability declares no side effects",
                side_effects=side_effects,
            )
        if side_effects == "local":
            if self._grant.allow_local:
                return AuthorityDecision(
                    allowed=True,
                    actor=ACTOR,
                    reason="local side effects are confined to the run workspace",
                    side_effects=side_effects,
                )
            return AuthorityDecision(
                allowed=False,
                actor=ACTOR,
                reason="local side effects were not granted (deny-by-default)",
                side_effects=side_effects,
            )
        if side_effects == "external":
            if self._grant.allow_external:
                return AuthorityDecision(
                    allowed=True,
                    actor=ACTOR,
                    reason="external authority was explicitly granted for this run",
                    side_effects=side_effects,
                )
            return AuthorityDecision(
                allowed=False,
                actor=ACTOR,
                reason=(
                    f"capability {stage.capability!r} declares external side effects "
                    "but no external authority was granted (deny-by-default)"
                ),
                side_effects=side_effects,
            )
        return AuthorityDecision(
            allowed=False,
            actor=ACTOR,
            reason=f"unknown side-effect class {side_effects!r} (deny-by-default)",
            side_effects=side_effects,
        )
