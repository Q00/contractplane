from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from contractplane.compiler import compile_plan
from contractplane.errors import LedgerError, TransitionError
from contractplane.ledger import JsonlLedger
from contractplane.loader import load_domain_pack, parse_domain_pack
from contractplane.state import (
    ExecutionMachine,
    ExecutionStatus,
    StageStatus,
    UnitRef,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = load_domain_pack(ROOT / "examples" / "hello-domain" / "domainpack.yaml")
PLAN = compile_plan(PACK, entrypoint_id="hello")


def _complete_normalize(machine: ExecutionMachine, key: str, value: str) -> UnitRef:
    ref = machine.register_unit("normalize", key)
    machine.start_unit(ref)
    machine.claim_unit(ref, {"value": value})
    machine.record_evidence(ref, "normalized-name-contract", {"value": value})
    assert machine.units[ref].status is StageStatus.COMPLETED
    return ref


def _complete_draft(machine: ExecutionMachine, key: str, greeting: str) -> UnitRef:
    ref = machine.register_unit("draft", key)
    machine.start_unit(ref)
    machine.claim_unit(ref, {"greeting": greeting})
    machine.record_evidence(ref, "greeting-review", {"verdict": "confirmed"})
    assert machine.units[ref].status is StageStatus.COMPLETED
    return ref


def test_work_units_gate_evidence_and_unlock_stage_barriers(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "ledger.jsonl")
    machine = ExecutionMachine.create(PLAN, ledger, "run-1")
    machine.start()
    assert machine.units == {}  # fanout.each is adapter-expanded, never guessed

    ada = _complete_normalize(machine, "ada", "Ada")
    grace = _complete_normalize(machine, "grace", "Grace")
    machine.seal_stage("normalize")
    assert machine.units[ada].status is StageStatus.COMPLETED
    assert machine.units[grace].status is StageStatus.COMPLETED

    _complete_draft(machine, "ada", "Hello, Ada!")
    _complete_draft(machine, "grace", "Hello, Grace!")
    machine.seal_stage("draft")

    publish = UnitRef("publish")
    archive = UnitRef("archive")
    assert machine.units[publish].status is StageStatus.AWAITING_AUTHORIZATION
    assert machine.units[archive].status is StageStatus.READY

    machine.skip_unit(archive, reason="adapter evaluated inputs.archive as false")
    machine.authorize_unit(publish, approved=True, actor="human:test")
    assert machine.units[publish].status is StageStatus.READY
    machine.start_unit(publish)
    machine.claim_unit(publish, {"receiptId": "pub-1"})
    assert machine.units[publish].status is StageStatus.AWAITING_EVIDENCE
    machine.record_evidence(publish, "publication-receipt", {"receiptId": "pub-1"})
    assert machine.units[publish].status is StageStatus.COMPLETED
    assert machine.status is ExecutionStatus.SUCCEEDED
    assert machine.snapshot()["apiVersion"] == "contractplane.dev/kernel-state/v0alpha1"

    replayed = ExecutionMachine.replay(PLAN, ledger, "run-1")
    assert replayed.snapshot() == machine.snapshot()

    for event in ledger.read("run-1"):
        if event["type"].startswith("unit.") or event["type"] == "evidence.recorded":
            assert event["payload"]["unit"]["unitKey"]


def test_invalid_evidence_cannot_advance_one_unit(tmp_path: Path) -> None:
    machine = ExecutionMachine.create(PLAN, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ref = machine.register_unit("normalize", "ada")
    machine.seal_stage("normalize")
    machine.start_unit(ref)
    machine.claim_unit(ref, {"value": "Ada"})
    with pytest.raises(TransitionError, match="does not satisfy"):
        machine.record_evidence(ref, "normalized-name-contract", {"value": ""})
    assert machine.units[ref].status is StageStatus.AWAITING_EVIDENCE
    assert machine.units[ref].evidence == {}


def test_units_retry_independently(tmp_path: Path) -> None:
    machine = ExecutionMachine.create(PLAN, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ada = machine.register_unit("normalize", "ada")
    grace = machine.register_unit("normalize", "grace")
    machine.seal_stage("normalize")
    machine.start_unit(ada)
    machine.fail_unit(ada, "transient adapter failure", retry=True)
    assert machine.units[ada].status is StageStatus.READY
    assert machine.units[ada].attempts == 1
    assert machine.units[grace].status is StageStatus.READY
    machine.start_unit(ada)
    assert machine.units[ada].attempts == 2
    machine.fail_unit(ada, "again", retry=True)
    assert machine.status is ExecutionStatus.FAILED
    assert machine.units[ada].status is StageStatus.FAILED
    assert machine.units[grace].status is StageStatus.READY


def test_cannot_claim_or_use_post_result_approval_around_required_gate(tmp_path: Path) -> None:
    machine = ExecutionMachine.create(PLAN, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ref = machine.register_unit("normalize", "ada")
    with pytest.raises(TransitionError, match="expected running"):
        machine.claim_unit(ref)
    machine.start_unit(ref)
    machine.claim_unit(ref, {"value": "Ada"})
    with pytest.raises(TransitionError, match="post-result approval is not implemented"):
        machine.approve_unit(ref, approved=True, actor="human")


def test_claim_must_satisfy_capability_output_schema(tmp_path: Path) -> None:
    machine = ExecutionMachine.create(PLAN, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ref = machine.register_unit("normalize", "ada")
    machine.start_unit(ref)
    with pytest.raises(TransitionError, match="output schema"):
        machine.claim_unit(ref, {"wrong": "shape"})
    assert machine.units[ref].status is StageStatus.RUNNING


def test_singleton_stage_is_kernel_materialized_and_condition_skip_is_checked(tmp_path: Path) -> None:
    simple_pack = load_domain_pack(ROOT / "conformance" / "valid" / "hello-domain.yaml")
    plan = compile_plan(simple_pack)
    machine = ExecutionMachine.create(plan, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ref = UnitRef("write")
    assert machine.units[ref].status is StageStatus.READY
    with pytest.raises(TransitionError, match="has no declarative when"):
        machine.skip_unit(ref, reason="false")


def test_replay_rejects_wrong_plan_and_duplicate_execution(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "l.jsonl")
    ExecutionMachine.create(PLAN, ledger, "run")
    with pytest.raises(LedgerError, match="already exists"):
        ExecutionMachine.create(PLAN, ledger, "run")
    other = compile_plan(PACK, flow_id="greet")
    # Same flow without an entrypoint has a different plan digest.
    with pytest.raises(LedgerError, match="plan digest mismatch"):
        ExecutionMachine.replay(other, ledger, "run")


def _single_stage_pack(*, approval: str = "never", fanout: str = "singleton"):
    raw = yaml.safe_load(
        (ROOT / "conformance" / "valid" / "hello-domain.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["policies"][0]["humanApproval"] = approval
    if fanout == "each":
        raw["flows"][0]["stages"][0]["fanout"] = {
            "mode": "each",
            "over": "$.items",
        }
    return parse_domain_pack(raw)


def test_human_approval_is_pre_dispatch_authorization(tmp_path: Path) -> None:
    plan = compile_plan(_single_stage_pack(approval="always"))
    machine = ExecutionMachine.create(plan, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ref = UnitRef("write")
    assert machine.units[ref].status is StageStatus.AWAITING_AUTHORIZATION
    assert machine.units[ref].attempts == 0
    with pytest.raises(TransitionError, match="expected ready"):
        machine.start_unit(ref)

    machine.authorize_unit(ref, approved=True, actor="director")
    assert machine.units[ref].status is StageStatus.READY
    machine.start_unit(ref)
    assert machine.units[ref].attempts == 1


def test_denied_pre_dispatch_authorization_never_starts_unit(tmp_path: Path) -> None:
    plan = compile_plan(_single_stage_pack(approval="always"))
    machine = ExecutionMachine.create(plan, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ref = UnitRef("write")
    machine.authorize_unit(ref, approved=False, actor="director", reason="not allowed")
    assert machine.units[ref].attempts == 0
    assert machine.units[ref].status is StageStatus.FAILED
    assert machine.status is ExecutionStatus.FAILED


def test_authorized_unit_retry_requires_fresh_pre_dispatch_authorization(tmp_path: Path) -> None:
    plan = compile_plan(_single_stage_pack(approval="always"))
    machine = ExecutionMachine.create(plan, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    ref = UnitRef("write")
    machine.authorize_unit(ref, approved=True, actor="director")
    machine.start_unit(ref)
    machine.fail_unit(ref, "retryable", retry=True)
    assert machine.units[ref].status is StageStatus.AWAITING_AUTHORIZATION
    assert machine.units[ref].attempts == 1
    with pytest.raises(TransitionError, match="expected ready"):
        machine.start_unit(ref)
    machine.authorize_unit(ref, approved=True, actor="director")
    machine.start_unit(ref)
    assert machine.units[ref].attempts == 2


def test_empty_each_fanout_cannot_seal_or_succeed(tmp_path: Path) -> None:
    plan = compile_plan(_single_stage_pack(fanout="each"))
    machine = ExecutionMachine.create(plan, JsonlLedger(tmp_path / "l.jsonl"), "run")
    machine.start()
    with pytest.raises(TransitionError, match="at least one unit"):
        machine.seal_stage("write")
    assert machine.status is ExecutionStatus.RUNNING
    assert machine.units == {}


def test_replay_rejects_forged_completion_without_gates(tmp_path: Path) -> None:
    plan = compile_plan(_single_stage_pack())
    ledger = JsonlLedger(tmp_path / "l.jsonl")
    machine = ExecutionMachine.create(plan, ledger, "run")
    machine.start()
    ref = UnitRef("write")
    ledger.append("run", "unit.completed", {"unit": ref.to_dict()})
    ledger.append("run", "execution.succeeded", {})
    with pytest.raises(LedgerError, match="cannot complete before all planned gates"):
        ExecutionMachine.replay(plan, ledger, "run")


def test_replay_rejects_forged_dispatch_without_authorization(tmp_path: Path) -> None:
    plan = compile_plan(_single_stage_pack(approval="always"))
    ledger = JsonlLedger(tmp_path / "l.jsonl")
    machine = ExecutionMachine.create(plan, ledger, "run")
    machine.start()
    ref = UnitRef("write")
    ledger.append("run", "unit.started", {"unit": ref.to_dict()})
    with pytest.raises(LedgerError, match="unit can start only from ready"):
        ExecutionMachine.replay(plan, ledger, "run")
