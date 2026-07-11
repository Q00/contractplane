"""Independent evidence verifier.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

The verifier is structurally separate from the producer. It is constructed
without any reference to the adapter, the worker subprocess, or the producer's
claimed outputs. To reach a verdict it re-derives the canonical artifact address
from the harness-owned :func:`~contractplane.experimental.workspace.evidence_artifact_path`,
reads the artifact from disk itself, confirms it is confined to the workspace,
and validates it against the *declared* evidence schema from the compiled plan.

A schema check alone is weak independence: it only proves the producer-authored
artifact is well-shaped, not that it is true. When a
:class:`~contractplane.experimental.recompute.Recomputer` is supplied, the
verifier goes further and recomputes the checked quantity **from the raw input
data itself** — never from the producer's artifact — and rejects any claim that
contradicts that independently computed ground truth. A producer that overclaims
(e.g. reports 100 rows when the source dataset holds 3) therefore passes schema
validation but is still rejected here, and the unit does not advance.

Honesty boundary: recomputation gives genuine independence only for evidence a
deterministic function can re-derive. The typed independence spectrum
(distinct-model and human verifiers, non-recomputable evidence) remains
specified-only. Only an accepted verdict is ever fed to the kernel's
``evidence.recorded`` transition, so only an accepted verdict advances a unit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from ..compiler import CompiledStage
from .recompute import Recomputer
from .workspace import Workspace

VERIFIER_ID = "independent-verifier"


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    evidence_id: str
    verifier: str
    reason: str
    method: str = "schema"
    receipt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "evidenceId": self.evidence_id,
            "verifier": self.verifier,
            "method": self.method,
            "reason": self.reason,
        }


class IndependentVerifier:
    """Check a stage's declared evidence obligation against produced artifacts."""

    def __init__(self, workspace: Workspace, recomputer: Recomputer | None = None):
        self._workspace = workspace
        self._recomputer = recomputer

    @staticmethod
    def _evidence_contract(stage: CompiledStage, evidence_id: str) -> dict[str, Any]:
        for contract in stage.evidence_contracts:
            if contract["id"] == evidence_id:
                return contract
        raise ValueError(
            f"evidence {evidence_id!r} is not declared by stage {stage.id!r}"
        )

    def _reject(self, evidence_id: str, reason: str, *, method: str = "schema",
                receipt: dict[str, Any] | None = None) -> Verdict:
        return Verdict(
            accepted=False,
            evidence_id=evidence_id,
            verifier=VERIFIER_ID,
            method=method,
            reason=reason,
            receipt=receipt or {},
        )

    def verify(
        self,
        stage: CompiledStage,
        evidence_id: str,
        inputs: dict[str, Any] | None = None,
    ) -> Verdict:
        contract = self._evidence_contract(stage, evidence_id)
        path = self._workspace.evidence_path(stage.id, evidence_id)

        # Confinement is a real check, not a claim: the address must resolve
        # inside the workspace and the file must actually be present there.
        if not self._workspace.contains(path):
            return self._reject(evidence_id, "evidence artifact path escapes the run workspace")
        if not path.is_file():
            return self._reject(evidence_id, "declared evidence artifact was not produced")

        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._reject(evidence_id, f"evidence artifact is unreadable or not JSON: {exc}")
        if not isinstance(artifact, dict):
            return self._reject(evidence_id, "evidence artifact must be a JSON object")

        schema = contract.get("schema")
        if schema is not None:
            errors = sorted(
                Draft202012Validator(schema).iter_errors(artifact),
                key=lambda error: list(error.absolute_path),
            )
            if errors:
                rendered = "; ".join(error.message for error in errors[:5])
                return self._reject(
                    evidence_id,
                    f"artifact violates the declared evidence schema: {rendered}",
                    receipt=artifact,
                )

        # Recomputation: compare the producer's claim against ground truth that
        # the verifier derives from the raw input, not from the producer's file.
        recomputed = False
        if self._recomputer is not None:
            try:
                expected = self._recomputer.recompute(stage, evidence_id, inputs or {})
            except Exception as exc:  # noqa: BLE001 - a recomputer fault must not accept
                return self._reject(
                    evidence_id,
                    f"ground-truth recomputation failed, refusing to accept: {exc}",
                    method="recomputation",
                    receipt=artifact,
                )
            if expected:
                recomputed = True
                mismatches = [
                    f"{field_name}: producer claimed {artifact.get(field_name)!r} "
                    f"but recomputed ground truth is {value!r}"
                    for field_name, value in expected.items()
                    if artifact.get(field_name) != value
                ]
                if mismatches:
                    return self._reject(
                        evidence_id,
                        "producer claim contradicts recomputed ground truth: "
                        + "; ".join(mismatches),
                        method="recomputation",
                        receipt=artifact,
                    )

        if recomputed:
            return Verdict(
                accepted=True,
                evidence_id=evidence_id,
                verifier=VERIFIER_ID,
                method="recomputation",
                reason="artifact satisfies the declared schema and matches recomputed ground truth",
                receipt=artifact,
            )
        return Verdict(
            accepted=True,
            evidence_id=evidence_id,
            verifier=VERIFIER_ID,
            method="schema",
            reason="artifact exists and satisfies the declared evidence schema",
            receipt=artifact,
        )
