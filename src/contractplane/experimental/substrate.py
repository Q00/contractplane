"""Cross-substrate governed study: local-process vs ACP.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

Substrate-neutrality is the founding thesis; this module measures it. It runs the
same governed conditions over TWO real substrates — the in-process
local-process subprocess adapter and the real ACP client adapter (which spawns
the Node ACP agent and drives a real ACP session) — and records a
``substrate x condition`` outcome table.

The two substrates share everything that defines the governed outcome: the same
compiled plan, the same authority gate, the same independent recompute-verifier,
and the same event-sourced kernel. They differ only in *how* the producer's work
and the authority permission travel:

* local-process: the kernel's pre-dispatch authorization gate enforces authority
  in-process; the subprocess worker produces the claim.
* acp: the ACP agent issues a real ``session/request_permission`` request that
  this client answers from the *same* authority decision, and the agent produces
  the claim over ACP ``session/update``.

The result to establish is that the governed outcome is identical down each
column pair, and that the deny path is exercised over real ACP messages.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..compiler import compile_plan
from ..ledger import JsonlLedger
from ..loader import load_domain_pack
from ..state import ExecutionMachine, UnitRef, UnitStatus
from .acp_adapter import acp_available, node_executable, run_acp_task
from .adapter import LocalProcessAdapter
from .authority import AuthorityGate, AuthorityGrant
from .episode import EPISODE_SCHEMA, EpisodeProducer, parse_episode
from .harness import GovernedRunner, RunResult
from .recompute import (
    ChainRecomputer,
    FilterCountRecomputer,
    RecordCountRecomputer,
    SumRecomputer,
)
from .verifier import IndependentVerifier
from .workspace import Workspace

STUDY_SCHEMA = "contractplane.dev/experimental/acp-substrate-study/v0"
SUBSTRATES: tuple[str, ...] = ("local-process", "acp")
_OUTCOME = {RunResult.SUCCEEDED: "accepted", RunResult.REJECTED: "rejected", RunResult.DENIED: "denied"}
STUDY_NOTE = (
    "EXPERIMENTAL cross-substrate study. Both substrates share the same plan, "
    "authority gate, recompute-verifier, and kernel; they differ only in transport "
    "(in-process subprocess vs real ACP session). The acp substrate answers ACP's "
    "session/request_permission from the same contract authority decision, so the "
    "deny path is exercised over real ACP messages."
)

# weekly-metrics has 3 records; the echo claims are recorded relative to that truth.
_WEEKLY_TRUE_ROWS = 3


@dataclass(frozen=True)
class ConditionSpec:
    flow: str
    inputs: dict[str, Any]
    mode: str  # "worker" | "echo"
    grant: AuthorityGrant | None
    expected: str
    claim: dict[str, Any] | None = None


def _report_claim(rows: int) -> dict[str, Any]:
    return {
        "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": rows},
        "artifact": {
            "report-artifact": {"dataset": "weekly-metrics", "rows": rows, "generatedBy": "compile-report"}
        },
    }


def condition_specs() -> dict[str, ConditionSpec]:
    return {
        "correct": ConditionSpec("report", {"dataset": "weekly-metrics"}, "worker", None, "accepted"),
        "overclaim": ConditionSpec(
            "report", {"dataset": "weekly-metrics"}, "echo", None, "rejected", _report_claim(100)
        ),
        "borderline": ConditionSpec(
            "report", {"dataset": "weekly-metrics"}, "echo", None, "rejected",
            _report_claim(_WEEKLY_TRUE_ROWS + 1),
        ),
        "authority-denied": ConditionSpec(
            "publish", {"artifact": "evidence/report.json"}, "worker", None, "denied"
        ),
        "authority-granted": ConditionSpec(
            "publish", {"artifact": "evidence/report.json"}, "worker",
            AuthorityGrant(allow_external=True), "accepted",
        ),
    }


def _recomputer(datasets_dir: Path) -> ChainRecomputer:
    return ChainRecomputer(
        [
            RecordCountRecomputer(datasets_dir),
            SumRecomputer(datasets_dir),
            FilterCountRecomputer(datasets_dir),
        ]
    )


def _echo_episode(spec: ConditionSpec):
    return parse_episode(
        {
            "schema": EPISODE_SCHEMA,
            "provenance": "synthetic-smoke",
            "flow": spec.flow,
            "input": spec.inputs,
            "claim": spec.claim,
        }
    )


def _run_local(spec, *, pack_dir, plan, datasets_dir, root: Path) -> dict[str, Any]:
    workspace = Workspace.create(root / "ws")
    ledger = JsonlLedger(root / "ledger.jsonl")
    producer = EpisodeProducer(_echo_episode(spec)) if spec.mode == "echo" else LocalProcessAdapter(pack_dir)
    runner = GovernedRunner(
        plan,
        pack_dir=pack_dir,
        workspace=workspace,
        ledger=ledger,
        authority=AuthorityGate(spec.grant),
        producer=producer,
        recomputer=_recomputer(datasets_dir),
    )
    report = runner.run(spec.inputs, execution_id="local")
    return {
        "substrate": "local-process",
        "outcome": _OUTCOME[report.result],
        "permissionChannel": "kernel-authorization",
        "verdictMethod": report.verdicts[-1].method if report.verdicts else None,
    }


def _build_task(spec, stage, *, pack_dir: Path, workspace: Workspace, python: str) -> dict[str, Any]:
    evidence_targets = {
        eid: str(workspace.evidence_path(stage.id, eid)) for eid in stage.requires_evidence
    }
    action = {
        "title": f"{stage.capability} over ACP",
        "capability": stage.capability,
        "sideEffects": stage.side_effects,
    }
    if spec.mode == "echo":
        return {"mode": "echo", "action": action, "evidenceTargets": evidence_targets, "claim": spec.claim}
    binding = stage.binding or {}
    config = binding.get("config") or {}
    entry = pack_dir / config["entry"]
    assignment = {
        "stage": stage.id,
        "capability": stage.capability,
        "target": binding.get("target"),
        "config": config,
        "input": spec.inputs,
        "evidenceTargets": evidence_targets,
    }
    assignment_path = workspace.dispatch_path(stage.id)
    assignment_path.write_text(json.dumps(assignment), encoding="utf-8")
    return {
        "mode": "worker",
        "action": action,
        "python": python,
        "worker": str(entry),
        "assignmentPath": str(assignment_path),
        "cwd": str(workspace.root),
    }


def _run_acp(spec, *, pack_dir, plan, datasets_dir, python, node, root: Path) -> dict[str, Any]:
    workspace = Workspace.create(root / "ws")
    ledger = JsonlLedger(root / "ledger.jsonl")
    authority = AuthorityGate(spec.grant)
    verifier = IndependentVerifier(workspace, recomputer=_recomputer(datasets_dir))
    machine = ExecutionMachine.create(plan, ledger, "acp")
    machine.start()
    stage = plan.stages[0]
    ref = UnitRef(stage.id)
    decision = authority.decide(stage)

    task = _build_task(spec, stage, pack_dir=pack_dir, workspace=workspace, python=python)
    acp = run_acp_task(task, allow=decision.allowed, cwd=workspace.root, node=node)

    def result(outcome: str, verdict_method: str | None = None) -> dict[str, Any]:
        return {
            "substrate": "acp",
            "outcome": outcome,
            "permissionChannel": "acp:session/request_permission",
            "permissionRequested": acp.permission_requested,
            "permissionAnswer": "allow" if decision.allowed else "deny",
            "acpProtocolVersion": acp.protocol_version,
            "acpStopReason": acp.stop_reason,
            "verdictMethod": verdict_method,
        }

    unit = machine.units[ref]
    if unit.status is UnitStatus.AWAITING_AUTHORIZATION:
        machine.authorize_unit(ref, approved=decision.allowed, actor="acp-permission", reason=decision.reason)
        if not decision.allowed:
            return result("denied")
    elif not decision.allowed:
        machine.cancel(reason=decision.reason)
        return result("denied")

    machine.start_unit(ref)
    machine.claim_unit(ref, acp.outputs or {})
    last_method: str | None = None
    for evidence_id in stage.requires_evidence:
        verdict = verifier.verify(stage, evidence_id, spec.inputs)
        last_method = verdict.method
        machine.record_evidence(ref, evidence_id, verdict.receipt, accepted=verdict.accepted)
        if not verdict.accepted:
            return result("rejected", verdict.method)
    return result("accepted", last_method)


def run_condition(name: str, spec: ConditionSpec, *, pack_dir, plans, datasets_dir, python, node) -> list[dict[str, Any]]:
    plan = plans[spec.flow]
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="substrate-local-") as scratch:
        row = _run_local(spec, pack_dir=pack_dir, plan=plan, datasets_dir=datasets_dir, root=Path(scratch))
        row.update({"condition": name, "expected": spec.expected})
        rows.append(row)
    if node is not None:
        with tempfile.TemporaryDirectory(prefix="substrate-acp-") as scratch:
            row = _run_acp(
                spec, pack_dir=pack_dir, plan=plan, datasets_dir=datasets_dir,
                python=python, node=node, root=Path(scratch),
            )
            row.update({"condition": name, "expected": spec.expected})
            rows.append(row)
    else:
        rows.append({"condition": name, "substrate": "acp", "skipped": "acp-unavailable", "expected": spec.expected})
    return rows


def run_substrate_study(*, pack_dir: Path, datasets_dir: Path, python: str) -> dict[str, Any]:
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plans = {
        "report": compile_plan(pack, entrypoint_id="report"),
        "publish": compile_plan(pack, entrypoint_id="publish"),
    }
    available, reason = acp_available()
    node = node_executable() if available else None
    specs = condition_specs()

    rows: list[dict[str, Any]] = []
    for name, spec in specs.items():
        rows.extend(
            run_condition(name, spec, pack_dir=pack_dir, plans=plans, datasets_dir=datasets_dir, python=python, node=node)
        )

    table: dict[str, dict[str, str]] = {s: {} for s in SUBSTRATES}
    for row in rows:
        substrate = row["substrate"]
        table.setdefault(substrate, {})[row["condition"]] = row.get("outcome") or f"skipped:{row.get('skipped')}"

    agreement = {}
    for name in specs:
        local = table["local-process"].get(name)
        acp = table["acp"].get(name)
        agreement[name] = {
            "local": local,
            "acp": acp,
            "agree": (acp is not None and not str(acp).startswith("skipped") and local == acp),
        }
    agree_count = sum(1 for a in agreement.values() if a["agree"])

    return {
        "schema": STUDY_SCHEMA,
        "note": STUDY_NOTE,
        "acpAvailable": available,
        "acpReason": reason,
        "substrates": list(SUBSTRATES),
        "conditions": list(specs),
        "rows": rows,
        "table": table,
        "agreement": agreement,
        "agreementCount": agree_count,
        "conditionsCount": len(specs),
    }


def write_substrate_study(report: dict[str, Any], out_path: str | Path) -> Path:
    target = Path(out_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
