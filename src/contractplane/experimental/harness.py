"""Governed run harness.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

:class:`GovernedRunner` closes the loop between the four pieces of this slice and
the frozen kernel. For each stage of a compiled plan it:

1. asks the :class:`~contractplane.experimental.authority.AuthorityGate` whether
   the stage's declared authority permits dispatch (deny-by-default);
2. feeds an ``always``-approval stage's decision into the kernel's existing
   pre-dispatch ``authorization.decided`` transition, so a denial fails the run
   and is recorded in the ledger;
3. dispatches the granted unit's work through the
   :class:`~contractplane.experimental.adapter.LocalProcessAdapter`;
4. records the producer's claim via the kernel's schema-gated ``claim_unit``; and
5. lets the *independent* verifier reach a verdict from artifacts on disk, then
   records that verdict through the kernel's ``evidence.recorded`` transition.

The runner only ever drives the kernel through its public methods; it invents no
new state and mints no verdict of its own. Scope is singleton stages only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..compiler import ExecutionPlan
from ..ledger import JsonlLedger
from ..state import ExecutionMachine, ExecutionStatus, UnitRef, UnitStatus
from .adapter import LocalProcessAdapter
from .authority import AuthorityDecision, AuthorityGate
from .recompute import Recomputer
from .verifier import IndependentVerifier, Verdict
from .workspace import Workspace


class ConfigurationError(RuntimeError):
    """The plan cannot be governed safely by this experimental harness."""


class RunResult(StrEnum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"
    REJECTED = "rejected"


@dataclass
class RunReport:
    result: RunResult
    execution_status: str
    execution_id: str
    plan_digest: str
    stage_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    authority_decisions: dict[str, AuthorityDecision] = field(default_factory=dict)
    verdicts: list[Verdict] = field(default_factory=list)
    denied_stage: str | None = None
    rejected_stage: str | None = None
    ledger_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.value,
            "executionStatus": self.execution_status,
            "executionId": self.execution_id,
            "planDigest": self.plan_digest,
            "stageOutputs": self.stage_outputs,
            "authorityDecisions": {
                stage_id: decision.to_dict()
                for stage_id, decision in self.authority_decisions.items()
            },
            "verdicts": [verdict.to_dict() for verdict in self.verdicts],
            "deniedStage": self.denied_stage,
            "rejectedStage": self.rejected_stage,
            "ledgerEvents": self.ledger_events,
        }


class GovernedRunner:
    def __init__(
        self,
        plan: ExecutionPlan,
        *,
        pack_dir: Path,
        workspace: Workspace,
        ledger: JsonlLedger,
        authority: AuthorityGate | None = None,
        adapter: LocalProcessAdapter | None = None,
        producer: Any | None = None,
        recomputer: Recomputer | None = None,
    ):
        self._plan = plan
        self._workspace = workspace
        self._ledger = ledger
        self._authority = authority or AuthorityGate()
        # A "producer" turns a stage into a claim plus on-disk artifacts. The
        # default is the local-process subprocess adapter; an episode runner
        # supplies a producer that replays a recorded LLM transcript instead.
        # Any producer must expose ``supports(stage)`` and
        # ``dispatch(stage, inputs, workspace) -> DispatchResult``.
        self._producer = producer or adapter or LocalProcessAdapter(pack_dir)
        self._verifier = IndependentVerifier(workspace, recomputer=recomputer)
        self._preflight()

    def _preflight(self) -> None:
        for stage in self._plan.stages:
            if stage.fanout.get("mode") != "singleton":
                raise ConfigurationError(
                    f"stage {stage.id!r} uses fanout {stage.fanout.get('mode')!r}; "
                    "this experimental harness governs singleton stages only"
                )
            if stage.side_effects == "external" and stage.policy["humanApproval"] != "always":
                raise ConfigurationError(
                    f"stage {stage.id!r} declares external side effects but its policy does not "
                    "require humanApproval; deny-by-default cannot be enforced pre-dispatch"
                )
            if not self._producer.supports(stage):
                raise ConfigurationError(
                    f"stage {stage.id!r} binding is not handled by the configured producer"
                )

    def run(self, inputs: dict[str, Any], *, execution_id: str) -> RunReport:
        errors = sorted(
            Draft202012Validator(self._plan.input_schema).iter_errors(inputs),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            rendered = "; ".join(error.message for error in errors[:5])
            raise ConfigurationError(f"flow inputs violate the plan input schema: {rendered}")

        machine = ExecutionMachine.create(self._plan, self._ledger, execution_id)
        machine.start()
        report = RunReport(
            result=RunResult.SUCCEEDED,
            execution_status=machine.status.value,
            execution_id=execution_id,
            plan_digest=self._plan.digest,
        )

        for stage in self._plan.stages:
            ref = UnitRef(stage.id)
            unit = machine.units.get(ref)
            if unit is None:
                raise ConfigurationError(
                    f"stage {stage.id!r} did not materialize a singleton unit; "
                    "its dependencies may not be satisfiable by this harness"
                )

            decision = self._authority.decide(stage)
            report.authority_decisions[stage.id] = decision

            if unit.status is UnitStatus.AWAITING_AUTHORIZATION:
                machine.authorize_unit(
                    ref,
                    approved=decision.allowed,
                    actor=decision.actor,
                    reason=decision.reason,
                )
                if not decision.allowed:
                    return self._finalize(machine, report, RunResult.DENIED, denied=stage.id)
            elif not decision.allowed:
                # A never-approval stage the kernel cannot gate pre-dispatch: refuse
                # to dispatch and cancel the run so the denial is still recorded.
                machine.cancel(reason=decision.reason)
                return self._finalize(machine, report, RunResult.DENIED, denied=stage.id)

            machine.start_unit(ref)
            dispatched = self._producer.dispatch(stage, inputs, self._workspace)
            report.stage_outputs[stage.id] = dispatched.outputs
            machine.claim_unit(ref, dispatched.outputs)

            for evidence_id in stage.requires_evidence:
                verdict = self._verifier.verify(stage, evidence_id, inputs)
                report.verdicts.append(verdict)
                machine.record_evidence(
                    ref, evidence_id, verdict.receipt, accepted=verdict.accepted
                )
                if not verdict.accepted:
                    return self._finalize(
                        machine, report, RunResult.REJECTED, rejected=stage.id
                    )

        return self._finalize(machine, report, RunResult.SUCCEEDED)

    def _finalize(
        self,
        machine: ExecutionMachine,
        report: RunReport,
        result: RunResult,
        *,
        denied: str | None = None,
        rejected: str | None = None,
    ) -> RunReport:
        report.result = result
        report.denied_stage = denied
        report.rejected_stage = rejected
        report.execution_status = machine.status.value
        report.ledger_events = len(self._ledger.read(report.execution_id))
        return report
