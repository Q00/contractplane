from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from jsonschema import Draft202012Validator

from .compiler import CompiledStage, ExecutionPlan
from .errors import LedgerError, TransitionError
from .ledger import LEDGER_SCHEMA_VERSION, JsonlLedger

STATE_API_VERSION = LEDGER_SCHEMA_VERSION
SINGLETON_UNIT_KEY = "default"


class ExecutionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UnitStatus(StrEnum):

    PENDING = "pending"
    AWAITING_AUTHORIZATION = "awaiting-authorization"
    READY = "ready"
    RUNNING = "running"
    CLAIMED = "claimed"
    AWAITING_EVIDENCE = "awaiting-evidence"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Compatibility alias for early callers; state is now explicitly work-unit keyed.
StageStatus = UnitStatus


@dataclass(frozen=True, order=True)
class UnitRef:
    stage_id: str
    unit_key: str = SINGLETON_UNIT_KEY

    def __post_init__(self) -> None:
        if not self.stage_id:
            raise ValueError("stage_id must not be empty")
        if not self.unit_key or any(char in self.unit_key for char in "\x00\r\n"):
            raise ValueError("unit_key must be nonempty and contain no control newlines")

    def to_dict(self) -> dict[str, str]:
        return {"stageId": self.stage_id, "unitKey": self.unit_key}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "UnitRef":
        return cls(stage_id=value["stageId"], unit_key=value["unitKey"])


@dataclass
class WorkUnitState:
    ref: UnitRef
    status: UnitStatus = UnitStatus.PENDING
    attempts: int = 0
    outputs: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    failure: str | None = None
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.ref.to_dict(),
            "status": self.status.value,
            "attempts": self.attempts,
            "outputs": self.outputs,
            "evidence": self.evidence,
            "failure": self.failure,
            "skipReason": self.skip_reason,
        }


@dataclass
class StageGroupState:
    stage_id: str
    sealed: bool = False
    units: dict[str, WorkUnitState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stageId": self.stage_id,
            "sealed": self.sealed,
            "units": [self.units[key].to_dict() for key in sorted(self.units)],
        }


class ExecutionMachine:
    """Event-sourced transition kernel keyed by concrete work units.

    Compiled stages are templates. The kernel auto-materializes singleton units,
    while adapters explicitly register ``fanout.each`` units and seal expansion.
    It never evaluates selectors/conditions or invokes a capability binding.
    Evidence receipts are shape-gated adapter inputs in v0alpha1; verifier
    identity, independence, and a portable Verdict model are explicitly not
    implemented by this experimental kernel.
    """

    def __init__(self, plan: ExecutionPlan, ledger: JsonlLedger, execution_id: str):
        if not execution_id:
            raise TransitionError("execution_id must not be empty")
        self.plan = plan
        self.ledger = ledger
        self.execution_id = execution_id
        self.status = ExecutionStatus.CREATED
        self._created_applied = False
        self.failure: str | None = None
        self.stage_groups = {
            stage.id: StageGroupState(stage.id) for stage in self.plan.stages
        }

    @classmethod
    def create(
        cls, plan: ExecutionPlan, ledger: JsonlLedger, execution_id: str
    ) -> "ExecutionMachine":
        machine = cls(plan, ledger, execution_id)
        payload = {
            "planDigest": plan.digest,
            "domain": plan.domain_name,
            "flow": plan.flow,
        }
        machine._validate_event("execution.created", payload)
        ledger.create_execution(execution_id, payload)
        machine._apply_event("execution.created", payload)
        return machine

    @classmethod
    def replay(
        cls, plan: ExecutionPlan, ledger: JsonlLedger, execution_id: str
    ) -> "ExecutionMachine":
        events = ledger.read(execution_id)
        if not events:
            raise LedgerError(f"execution {execution_id!r} does not exist in {ledger.path}")
        first = events[0]
        if first["type"] != "execution.created":
            raise LedgerError("first execution event must be execution.created")
        recorded_digest = first["payload"].get("planDigest")
        if recorded_digest != plan.digest:
            raise LedgerError(
                f"plan digest mismatch: ledger has {recorded_digest!r}, current plan is {plan.digest!r}"
            )
        machine = cls(plan, ledger, execution_id)
        for event in events:
            try:
                machine._validate_event(event["type"], event["payload"])
                machine._apply_event(event["type"], event["payload"])
            except (KeyError, TypeError, ValueError, TransitionError, LedgerError) as exc:
                raise LedgerError(
                    f"invalid event sequence at ledger sequence {event['sequence']} "
                    f"({event['type']}): {exc}"
                ) from exc
        return machine

    @property
    def units(self) -> dict[UnitRef, WorkUnitState]:
        return {
            unit.ref: unit
            for group in self.stage_groups.values()
            for unit in group.units.values()
        }

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._validate_event(event_type, payload)
        self.ledger.append(self.execution_id, event_type, payload)
        self._apply_event(event_type, payload)

    def _stage_contract(self, stage_id: str) -> CompiledStage:
        try:
            return self.plan.stage_map[stage_id]
        except KeyError as exc:
            raise TransitionError(f"unknown stage {stage_id!r}") from exc

    def _group(self, stage_id: str) -> StageGroupState:
        try:
            return self.stage_groups[stage_id]
        except KeyError as exc:
            raise TransitionError(f"unknown stage {stage_id!r}") from exc

    def _unit(self, ref: UnitRef) -> WorkUnitState:
        self._stage_contract(ref.stage_id)
        try:
            return self.stage_groups[ref.stage_id].units[ref.unit_key]
        except KeyError as exc:
            raise TransitionError(
                f"unknown work unit {ref.stage_id!r}/{ref.unit_key!r}"
            ) from exc

    def _require_execution(self, expected: ExecutionStatus) -> None:
        if self.status is not expected:
            raise TransitionError(
                f"execution is {self.status.value}, expected {expected.value}"
            )

    def _require_unit(self, ref: UnitRef, expected: StageStatus) -> WorkUnitState:
        unit = self._unit(ref)
        if unit.status is not expected:
            raise TransitionError(
                f"unit {ref.stage_id!r}/{ref.unit_key!r} is {unit.status.value}, "
                f"expected {expected.value}"
            )
        return unit

    @staticmethod
    def _ref_from_payload(payload: dict[str, Any]) -> UnitRef:
        unit = payload.get("unit")
        if not isinstance(unit, dict):
            raise LedgerError("unit event is missing its UnitRef")
        return UnitRef.from_dict(unit)

    def _all_work_satisfied(self) -> bool:
        return all(
            group.sealed
            and bool(group.units)
            and all(
                unit.status in {StageStatus.COMPLETED, StageStatus.SKIPPED}
                for unit in group.units.values()
            )
            for group in self.stage_groups.values()
        )

    def _validate_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Validate one event against current state before append or replay apply."""
        if not isinstance(payload, dict):
            raise TransitionError("event payload must be an object")
        if event_type == "execution.created":
            if self._created_applied:
                raise TransitionError("execution.created may appear only once")
            if payload.get("planDigest") != self.plan.digest:
                raise TransitionError("execution.created plan digest does not match the plan")
            if payload.get("domain") != self.plan.domain_name or payload.get("flow") != self.plan.flow:
                raise TransitionError("execution.created domain/flow does not match the plan")
            return
        if not self._created_applied:
            raise TransitionError("execution.created must be the first event")
        if event_type == "execution.started":
            if self.status is not ExecutionStatus.CREATED:
                raise TransitionError("execution can start only from created")
            return
        if event_type == "execution.succeeded":
            if self.status is not ExecutionStatus.RUNNING or not self._all_work_satisfied():
                raise TransitionError("execution cannot succeed before every sealed unit is satisfied")
            return
        if event_type == "execution.failed":
            if self.status is not ExecutionStatus.RUNNING:
                raise TransitionError("execution can fail only while running")
            ref = self._ref_from_payload(payload)
            if self._unit(ref).status is not StageStatus.FAILED:
                raise TransitionError("execution.failed requires a failed work unit")
            if not str(payload.get("reason", "")).strip():
                raise TransitionError("execution.failed requires a reason")
            return
        if event_type == "execution.cancelled":
            if self.status not in {ExecutionStatus.CREATED, ExecutionStatus.RUNNING}:
                raise TransitionError("execution cannot be cancelled from its current state")
            return

        if self.status is not ExecutionStatus.RUNNING:
            raise TransitionError(f"{event_type} requires a running execution")

        if event_type == "stage.sealed":
            stage_id = payload["stageId"]
            contract = self._stage_contract(stage_id)
            group = self._group(stage_id)
            if group.sealed:
                raise TransitionError(f"stage {stage_id!r} is already sealed")
            if not self.dependencies_satisfied(stage_id):
                raise TransitionError(f"stage {stage_id!r} dependencies are not satisfied")
            if not group.units:
                raise TransitionError(f"stage {stage_id!r} cannot seal without at least one unit")
            if contract.fanout["mode"] == "singleton" and set(group.units) != {
                SINGLETON_UNIT_KEY
            }:
                raise TransitionError("singleton stage must contain exactly its default unit")
            return

        ref = self._ref_from_payload(payload)
        contract = self._stage_contract(ref.stage_id)
        group = self._group(ref.stage_id)

        if event_type == "unit.registered":
            if group.sealed:
                raise TransitionError(f"stage {ref.stage_id!r} expansion is already sealed")
            if ref.unit_key in group.units:
                raise TransitionError("work unit is already registered")
            if not self.dependencies_satisfied(ref.stage_id):
                raise TransitionError(f"stage {ref.stage_id!r} dependencies are not satisfied")
            if contract.fanout["mode"] == "singleton":
                if ref.unit_key != SINGLETON_UNIT_KEY or group.units:
                    raise TransitionError("singleton stage accepts only one default unit")
            return

        unit = self._unit(ref)
        if event_type == "authorization.requested":
            if contract.policy["humanApproval"] != "always":
                raise TransitionError("authorization is not required by this unit policy")
            initial_request = unit.status is StageStatus.PENDING
            retry_request = unit.status is StageStatus.FAILED and payload.get("retry") is True
            if not (initial_request or retry_request):
                raise TransitionError(
                    "authorization can be requested only for a pending unit or approved retry"
                )
            if retry_request and unit.attempts >= int(contract.policy["maxAttempts"]):
                raise TransitionError("unit exhausted its retry policy")
            return
        if event_type == "authorization.decided":
            if unit.status is not StageStatus.AWAITING_AUTHORIZATION:
                raise TransitionError("authorization decision has no open request")
            if not isinstance(payload.get("approved"), bool):
                raise TransitionError("authorization decision requires approved: boolean")
            if not str(payload.get("actor", "")).strip():
                raise TransitionError("authorization actor must not be empty")
            return
        if event_type == "unit.ready":
            first_ready = unit.status is StageStatus.PENDING
            retry_ready = unit.status is StageStatus.FAILED and payload.get("retry") is True
            if not (first_ready or retry_ready):
                raise TransitionError("unit.ready is invalid from the current unit state")
            if first_ready and contract.policy["humanApproval"] == "always":
                raise TransitionError("unit requires pre-dispatch authorization")
            if retry_ready and unit.attempts >= int(contract.policy["maxAttempts"]):
                raise TransitionError("unit exhausted its retry policy")
            return
        if event_type == "unit.started":
            if unit.status is not StageStatus.READY:
                raise TransitionError("unit can start only from ready")
            if unit.attempts >= int(contract.policy["maxAttempts"]):
                raise TransitionError("unit exhausted its retry policy")
            return
        if event_type == "unit.claimed":
            if unit.status is not StageStatus.RUNNING:
                raise TransitionError("claim requires a running unit")
            outputs = payload.get("outputs")
            if not isinstance(outputs, dict):
                raise TransitionError("claim outputs must be an object")
            errors = sorted(
                Draft202012Validator(contract.output_schema).iter_errors(outputs),
                key=lambda error: list(error.absolute_path),
            )
            if errors:
                raise TransitionError(
                    "claim does not satisfy output schema: "
                    + "; ".join(error.message for error in errors[:5])
                )
            return
        if event_type == "unit.awaiting-evidence":
            if unit.status is not StageStatus.CLAIMED:
                raise TransitionError("evidence gate requires a claimed unit")
            if not contract.requires_evidence:
                raise TransitionError("unit has no evidence obligations")
            if payload.get("required") != list(contract.requires_evidence):
                raise TransitionError("event evidence obligations do not match the plan")
            return
        if event_type == "evidence.recorded":
            if unit.status is not StageStatus.AWAITING_EVIDENCE:
                raise TransitionError("evidence requires an awaiting-evidence unit")
            evidence_id = payload.get("evidence")
            evidence_contract = self._evidence_contract(contract, evidence_id)
            if evidence_id in unit.evidence:
                raise TransitionError("evidence was already recorded for this unit")
            if not isinstance(payload.get("accepted"), bool):
                raise TransitionError("evidence event requires accepted: boolean")
            receipt = payload.get("receipt")
            if not isinstance(receipt, dict):
                raise TransitionError("evidence receipt must be an object")
            if payload["accepted"] and "schema" in evidence_contract:
                errors = sorted(
                    Draft202012Validator(evidence_contract["schema"]).iter_errors(receipt),
                    key=lambda error: list(error.absolute_path),
                )
                if errors:
                    raise TransitionError(
                        "evidence does not satisfy its schema: "
                        + "; ".join(error.message for error in errors[:5])
                    )
            return
        if event_type == "unit.completed":
            if unit.status is StageStatus.CLAIMED and not contract.requires_evidence:
                return
            if unit.status is StageStatus.AWAITING_EVIDENCE and all(
                unit.evidence.get(required, {}).get("accepted")
                for required in contract.requires_evidence
            ):
                return
            raise TransitionError("unit cannot complete before all planned gates are accepted")
        if event_type == "unit.skipped":
            if unit.status is not StageStatus.READY:
                raise TransitionError("unit cannot be skipped from its current state")
            if contract.when is None:
                raise TransitionError("unit has no declarative condition")
            if payload.get("when") != contract.when or not str(payload.get("reason", "")).strip():
                raise TransitionError("skip must preserve the condition and a nonempty reason")
            return
        if event_type == "unit.failed":
            if unit.status not in {
                StageStatus.RUNNING,
                StageStatus.CLAIMED,
                StageStatus.AWAITING_EVIDENCE,
            }:
                raise TransitionError("unit cannot fail from its current state")
            if not str(payload.get("reason", "")).strip():
                raise TransitionError("unit failure requires a reason")
            return
        raise TransitionError(f"unknown execution event type {event_type!r}")

    def _apply_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "execution.created":
            self._created_applied = True
            self.status = ExecutionStatus.CREATED
        elif event_type == "execution.started":
            self.status = ExecutionStatus.RUNNING
        elif event_type == "execution.succeeded":
            self.status = ExecutionStatus.SUCCEEDED
        elif event_type == "execution.failed":
            self.status = ExecutionStatus.FAILED
            self.failure = payload.get("reason")
        elif event_type == "execution.cancelled":
            self.status = ExecutionStatus.CANCELLED
            self.failure = payload.get("reason")
            for unit in self.units.values():
                if unit.status not in {
                    StageStatus.COMPLETED,
                    StageStatus.SKIPPED,
                    StageStatus.FAILED,
                }:
                    unit.status = StageStatus.CANCELLED
        elif event_type == "stage.sealed":
            self.stage_groups[payload["stageId"]].sealed = True
        elif event_type == "unit.registered":
            ref = self._ref_from_payload(payload)
            self.stage_groups[ref.stage_id].units[ref.unit_key] = WorkUnitState(ref)
        elif event_type == "authorization.requested":
            unit = self._unit(self._ref_from_payload(payload))
            unit.status = StageStatus.AWAITING_AUTHORIZATION
            if payload.get("retry") is True:
                unit.outputs = {}
                unit.evidence = {}
                unit.failure = None
                unit.skip_reason = None
        elif event_type == "authorization.decided":
            unit = self._unit(self._ref_from_payload(payload))
            if payload["approved"]:
                unit.status = StageStatus.READY
            else:
                unit.status = StageStatus.FAILED
                unit.failure = payload.get("reason") or "authorization denied"
        elif event_type == "unit.ready":
            unit = self._unit(self._ref_from_payload(payload))
            unit.status = StageStatus.READY
            unit.outputs = {}
            unit.evidence = {}
            unit.failure = None
            unit.skip_reason = None
        elif event_type == "unit.started":
            unit = self._unit(self._ref_from_payload(payload))
            unit.status = StageStatus.RUNNING
            unit.attempts += 1
        elif event_type == "unit.claimed":
            unit = self._unit(self._ref_from_payload(payload))
            unit.status = StageStatus.CLAIMED
            unit.outputs = payload["outputs"]
        elif event_type == "unit.awaiting-evidence":
            self._unit(self._ref_from_payload(payload)).status = StageStatus.AWAITING_EVIDENCE
        elif event_type == "evidence.recorded":
            unit = self._unit(self._ref_from_payload(payload))
            unit.evidence[payload["evidence"]] = {
                "accepted": payload["accepted"],
                "payload": payload["receipt"],
            }
        elif event_type == "unit.completed":
            self._unit(self._ref_from_payload(payload)).status = StageStatus.COMPLETED
        elif event_type == "unit.skipped":
            unit = self._unit(self._ref_from_payload(payload))
            unit.status = StageStatus.SKIPPED
            unit.skip_reason = payload["reason"]
        elif event_type == "unit.failed":
            unit = self._unit(self._ref_from_payload(payload))
            unit.status = StageStatus.FAILED
            unit.failure = payload["reason"]
        else:
            raise LedgerError(f"unknown execution event type {event_type!r}")

    def start(self) -> None:
        self._require_execution(ExecutionStatus.CREATED)
        self._emit("execution.started", {})
        self._materialize_singletons()

    def dependencies_satisfied(self, stage_id: str) -> bool:
        contract = self._stage_contract(stage_id)
        for dependency_id in contract.needs:
            group = self._group(dependency_id)
            if not group.sealed:
                return False
            if any(
                unit.status not in {StageStatus.COMPLETED, StageStatus.SKIPPED}
                for unit in group.units.values()
            ):
                return False
        return True

    def register_unit(self, stage_id: str, unit_key: str) -> UnitRef:
        """Materialize one adapter-expanded unit for a ``fanout.each`` template."""
        self._require_execution(ExecutionStatus.RUNNING)
        contract = self._stage_contract(stage_id)
        group = self._group(stage_id)
        if contract.fanout["mode"] != "each":
            raise TransitionError(
                f"stage {stage_id!r} is singleton; its default unit is kernel-managed"
            )
        if group.sealed:
            raise TransitionError(f"stage {stage_id!r} expansion is already sealed")
        if not self.dependencies_satisfied(stage_id):
            raise TransitionError(f"stage {stage_id!r} dependencies are not satisfied")
        ref = UnitRef(stage_id, unit_key)
        if ref.unit_key in group.units:
            raise TransitionError(
                f"work unit {stage_id!r}/{unit_key!r} is already registered"
            )
        self._emit("unit.registered", {"unit": ref.to_dict()})
        self._request_authorization_or_ready(ref)
        return ref

    def seal_stage(self, stage_id: str) -> None:
        """Declare that an adapter will register no more fanout units."""
        self._require_execution(ExecutionStatus.RUNNING)
        contract = self._stage_contract(stage_id)
        group = self._group(stage_id)
        if contract.fanout["mode"] != "each":
            raise TransitionError(f"singleton stage {stage_id!r} is sealed automatically")
        if group.sealed:
            raise TransitionError(f"stage {stage_id!r} is already sealed")
        if not self.dependencies_satisfied(stage_id):
            raise TransitionError(f"stage {stage_id!r} dependencies are not satisfied")
        if not group.units:
            raise TransitionError(f"stage {stage_id!r} cannot seal without at least one unit")
        self._emit("stage.sealed", {"stageId": stage_id})
        self._unlock_or_finish()

    def _request_authorization_or_ready(self, ref: UnitRef) -> None:
        contract = self._stage_contract(ref.stage_id)
        if contract.policy["humanApproval"] == "always":
            self._emit("authorization.requested", {"unit": ref.to_dict()})
        else:
            self._emit("unit.ready", {"unit": ref.to_dict()})

    def authorize_unit(
        self,
        ref: UnitRef,
        *,
        approved: bool,
        actor: str,
        reason: str = "",
    ) -> None:
        """Decide the pre-dispatch authorization required by unit policy."""
        self._require_execution(ExecutionStatus.RUNNING)
        self._require_unit(ref, StageStatus.AWAITING_AUTHORIZATION)
        if not actor.strip():
            raise TransitionError("authorization actor must not be empty")
        self._emit(
            "authorization.decided",
            {
                "unit": ref.to_dict(),
                "approved": bool(approved),
                "actor": actor,
                "reason": reason,
            },
        )
        if not approved:
            self._emit(
                "execution.failed",
                {
                    "unit": ref.to_dict(),
                    "reason": reason or "authorization denied",
                    "attempts": self._unit(ref).attempts,
                },
            )

    def start_unit(self, ref: UnitRef) -> None:
        self._require_execution(ExecutionStatus.RUNNING)
        unit = self._require_unit(ref, StageStatus.READY)
        contract = self._stage_contract(ref.stage_id)
        max_attempts = int(contract.policy["maxAttempts"])
        if unit.attempts >= max_attempts:
            raise TransitionError(
                f"unit {ref.stage_id!r}/{ref.unit_key!r} exhausted maxAttempts={max_attempts}"
            )
        self._emit("unit.started", {"unit": ref.to_dict()})

    def claim_unit(self, ref: UnitRef, outputs: dict[str, Any] | None = None) -> None:
        """Record a worker claim, then route that one unit to mandatory gates."""
        self._require_execution(ExecutionStatus.RUNNING)
        self._require_unit(ref, StageStatus.RUNNING)
        contract = self._stage_contract(ref.stage_id)
        claimed_outputs = outputs or {}
        errors = sorted(
            Draft202012Validator(contract.output_schema).iter_errors(claimed_outputs),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            rendered = "; ".join(error.message for error in errors[:5])
            raise TransitionError(
                f"claim for unit {ref.stage_id!r}/{ref.unit_key!r} does not satisfy "
                f"the capability output schema: {rendered}"
            )
        self._emit("unit.claimed", {"unit": ref.to_dict(), "outputs": claimed_outputs})
        if contract.requires_evidence:
            self._emit(
                "unit.awaiting-evidence",
                {"unit": ref.to_dict(), "required": list(contract.requires_evidence)},
            )
        else:
            self._complete_unit(ref)

    @staticmethod
    def _evidence_contract(stage: CompiledStage, evidence_id: str) -> dict[str, Any]:
        for contract in stage.evidence_contracts:
            if contract["id"] == evidence_id:
                return contract
        raise TransitionError(
            f"evidence {evidence_id!r} is not required by stage {stage.id!r}"
        )

    def record_evidence(
        self,
        ref: UnitRef,
        evidence_id: str,
        receipt: dict[str, Any],
        *,
        accepted: bool = True,
    ) -> None:
        self._require_execution(ExecutionStatus.RUNNING)
        unit = self._require_unit(ref, StageStatus.AWAITING_EVIDENCE)
        stage = self._stage_contract(ref.stage_id)
        evidence_contract = self._evidence_contract(stage, evidence_id)
        if evidence_id in unit.evidence:
            raise TransitionError(
                f"evidence {evidence_id!r} was already recorded for "
                f"unit {ref.stage_id!r}/{ref.unit_key!r}"
            )
        if not isinstance(receipt, dict):
            raise TransitionError("evidence receipt must be a JSON object")
        if accepted and "schema" in evidence_contract:
            errors = sorted(
                Draft202012Validator(evidence_contract.get("schema", {})).iter_errors(receipt),
                key=lambda error: list(error.absolute_path),
            )
            if errors:
                rendered = "; ".join(error.message for error in errors[:5])
                raise TransitionError(
                    f"evidence {evidence_id!r} does not satisfy its JSON Schema: {rendered}"
                )
        self._emit(
            "evidence.recorded",
            {
                "unit": ref.to_dict(),
                "evidence": evidence_id,
                "accepted": bool(accepted),
                "receipt": receipt,
            },
        )
        if not accepted:
            self.fail_unit(ref, f"evidence {evidence_id!r} was rejected")
            return
        if all(
            unit.evidence.get(required, {}).get("accepted")
            for required in stage.requires_evidence
        ):
            self._complete_unit(ref)

    def approve_unit(
        self,
        ref: UnitRef,
        *,
        approved: bool,
        actor: str,
        reason: str = "",
    ) -> None:
        raise TransitionError(
            "post-result approval is not implemented by the experimental kernel; "
            "use authorize_unit() before start_unit()"
        )

    def skip_unit(self, ref: UnitRef, *, reason: str) -> None:
        """Record an adapter-evaluated false condition; the kernel never evaluates it."""
        self._require_execution(ExecutionStatus.RUNNING)
        self._require_unit(ref, StageStatus.READY)
        contract = self._stage_contract(ref.stage_id)
        if contract.when is None:
            raise TransitionError(f"stage {ref.stage_id!r} has no declarative when condition")
        if not reason.strip():
            raise TransitionError("skip reason must not be empty")
        self._emit(
            "unit.skipped",
            {"unit": ref.to_dict(), "when": contract.when, "reason": reason},
        )
        self._unlock_or_finish()

    def fail_unit(self, ref: UnitRef, reason: str, *, retry: bool = False) -> None:
        self._require_execution(ExecutionStatus.RUNNING)
        unit = self._unit(ref)
        if unit.status not in {
            StageStatus.RUNNING,
            StageStatus.CLAIMED,
            StageStatus.AWAITING_EVIDENCE,
        }:
            raise TransitionError(
                f"unit {ref.stage_id!r}/{ref.unit_key!r} cannot fail from {unit.status.value}"
            )
        if not reason.strip():
            raise TransitionError("failure reason must not be empty")
        self._emit("unit.failed", {"unit": ref.to_dict(), "reason": reason})
        max_attempts = int(self._stage_contract(ref.stage_id).policy["maxAttempts"])
        if retry and unit.attempts < max_attempts:
            contract = self._stage_contract(ref.stage_id)
            if contract.policy["humanApproval"] == "always":
                self._emit(
                    "authorization.requested",
                    {"unit": ref.to_dict(), "retry": True},
                )
            else:
                self._emit("unit.ready", {"unit": ref.to_dict(), "retry": True})
        else:
            self._emit(
                "execution.failed",
                {
                    "unit": ref.to_dict(),
                    "reason": reason,
                    "attempts": unit.attempts,
                },
            )

    def cancel(self, reason: str = "cancelled by caller") -> None:
        if self.status not in {ExecutionStatus.CREATED, ExecutionStatus.RUNNING}:
            raise TransitionError(f"cannot cancel an execution in {self.status.value}")
        self._emit("execution.cancelled", {"reason": reason})

    def _complete_unit(self, ref: UnitRef) -> None:
        unit = self._unit(ref)
        if unit.status not in {
            StageStatus.CLAIMED,
            StageStatus.AWAITING_EVIDENCE,
        }:
            raise TransitionError(
                f"unit {ref.stage_id!r}/{ref.unit_key!r} cannot complete from {unit.status.value}"
            )
        self._emit("unit.completed", {"unit": ref.to_dict()})
        self._unlock_or_finish()

    def _materialize_singletons(self) -> None:
        for contract in self.plan.stages:
            group = self.stage_groups[contract.id]
            if (
                contract.fanout["mode"] == "singleton"
                and not group.units
                and self.dependencies_satisfied(contract.id)
            ):
                ref = UnitRef(contract.id)
                self._emit("unit.registered", {"unit": ref.to_dict()})
                self._request_authorization_or_ready(ref)
                self._emit("stage.sealed", {"stageId": contract.id})

    def _unlock_or_finish(self) -> None:
        self._materialize_singletons()
        if self._all_work_satisfied():
            self._emit("execution.succeeded", {})

    def snapshot(self) -> dict[str, Any]:
        return {
            "apiVersion": STATE_API_VERSION,
            "kind": "ExecutionState",
            "executionId": self.execution_id,
            "planDigest": self.plan.digest,
            "status": self.status.value,
            "failure": self.failure,
            "stages": [
                self.stage_groups[stage.id].to_dict() for stage in self.plan.stages
            ],
        }
