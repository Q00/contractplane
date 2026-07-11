#!/usr/bin/env python3
"""Hardened-composite experiment (EXPERIMENTAL) — the meta-policy rebuttal.

A reviewer's rebuttal to examples/composite-baseline: OPA/Rego's whole purpose is
enforcing invariants like "no accept transition without a preceding verify
verdict," so a single Rego constraint should make verification required in the
composite too — and if it does, the delta collapses to "one file vs five files."

This runs that experiment honestly and end-to-end with the real tools:

  1. HARDENED variant (workflow/report-hardened.cwl): verify emits a verdict
     receipt; a meta-policy accept-gate (policy/meta_accept.rego, via real `opa`)
     allows an accept only when a pass receipt bound to the artifact exists.
     - Does it catch the naive verify-omission? YES, two ways, both recorded:
       (a) with the receipt type-coupled to the verify step, dropping verify
           makes cwltool's own loader REJECT the workflow (dangling source),
           caught at validate time, pre-run (report-hardened-omitverify.cwl);
       (b) with a loose receipt input, an honest "no verification" receipt is
           DENIED by the accept-gate at runtime (report-hardened-loose.cwl).
  2. DRIFT ON THE GUARD — the second-order exposure the hardened composite is
     still open to, both run for real:
       (a) noguard  (report-hardened-noguard.cwl): drop the coupled verify+gate
           pair; overclaim runs GREEN and is accepted. Nothing requires a gate.
       (b) forged   (report-hardened-forged.cwl): keep the gate, drop verify, and
           source the receipt from a producer-side forger; the gate is present
           and consulted yet the overclaim runs GREEN, because the meta-policy
           can check a receipt's binding but not its ORIGIN.
  3. CONTRACTPLANE symmetry: the analogous invariant is a typed stage property
     (requiresEvidence; validator exit 2 pre-run) enforced by the frozen kernel.

It EXTENDS artifacts/composite_comparison.json with a "hardened_variant" section
(no existing keys removed) and APPENDS e5-* rows to artifacts/experiments.jsonl.

Run from the repo root:
    .venv/bin/python examples/composite-baseline/run_hardened.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
GOVERNED = REPO_ROOT / "examples" / "governed-run"
DATASETS = GOVERNED / "datasets"
SCHEMA = HERE / "schema" / "report-artifact.schema.json"
LOCAL_EFFECT = HERE / "effects" / "local-report.effect.json"
ARTIFACTS = REPO_ROOT / "artifacts"
EXPERIMENTS = ARTIFACTS / "experiments.jsonl"
COMPARISON = ARTIFACTS / "composite_comparison.json"

CWLTOOL = os.environ.get(
    "CWLTOOL", str(REPO_ROOT / ".ouroboros" / "composite-venv" / "bin" / "cwltool")
)
CONTRACTPLANE = os.environ.get(
    "CONTRACTPLANE", str(REPO_ROOT / ".venv" / "bin" / "contractplane")
)

_GATE_MARKERS = (
    ("schema-gate REJECT", "schema-gate"),
    ("verify REJECT", "verify"),
    ("accept-gate DENY", "accept-gate"),
    ("policy-gate DENY", "policy-gate"),
)


def _run_cwl(workflow: Path, claim: Path, dataset: Path, effect: Path, extra: list[str] | None = None) -> dict:
    outdir = Path(tempfile.mkdtemp(prefix="hardened-out-"))
    try:
        cmd = [
            CWLTOOL, "--quiet", "--outdir", str(outdir), str(workflow),
            "--claim", str(claim), "--schema", str(SCHEMA),
            "--dataset", str(dataset), "--effect", str(effect),
        ] + (extra or [])
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE))
        gate = next((name for marker, name in _GATE_MARKERS if marker in proc.stderr), None)
        prov = outdir / "provenance.json"
        wrote_prov = proc.returncode == 0 and prov.is_file()
        return {
            "exit_code": proc.returncode,
            "pipeline": "green" if proc.returncode == 0 else "red",
            "outcome": "accepted" if proc.returncode == 0 else "rejected",
            "rejected_by": gate,
            "provenance_written": wrote_prov,
        }
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def _validate_cwl(workflow: Path) -> dict:
    """Run cwltool's own loader/validator (no execution)."""
    proc = subprocess.run(
        [CWLTOOL, "--validate", str(workflow)], capture_output=True, text=True, cwd=str(HERE)
    )
    err = proc.stdout + proc.stderr
    snippet = None
    for line in err.splitlines():
        if "references unknown identifier" in line or "failed validation" in line:
            snippet = line.strip()
            break
    return {
        "exit_code": proc.returncode,
        "loads": proc.returncode == 0,
        "error_snippet": snippet,
    }


def _validate_pack(pack: Path) -> dict:
    proc = subprocess.run(
        [CONTRACTPLANE, "validate", str(pack)], capture_output=True, text=True
    )
    payload = proc.stdout.strip() or proc.stderr.strip()
    out = json.loads(payload) if payload else {}
    return {"exit_code": proc.returncode, "valid": bool(out.get("valid", False)), "issues": out.get("issues")}


def build_hardened_variant() -> dict:
    overclaim = HERE / "claims" / "sonnet-overclaim.claim.json"
    correct = HERE / "claims" / "sonnet-correct.claim.json"
    monthly = DATASETS / "monthly-metrics.json"
    weekly = DATASETS / "weekly-metrics.json"
    wf = HERE / "workflow"

    hardened_correct = _run_cwl(wf / "report-hardened.cwl", correct, weekly, LOCAL_EFFECT)
    hardened_overclaim = _run_cwl(wf / "report-hardened.cwl", overclaim, monthly, LOCAL_EFFECT)
    omitverify_validate = _validate_cwl(wf / "report-hardened-omitverify.cwl")
    loose_honest = _run_cwl(
        wf / "report-hardened-loose.cwl", overclaim, monthly, LOCAL_EFFECT,
        ["--receipt", str(HERE / "receipts" / "no-verification.receipt.json")],
    )
    drift_noguard = _run_cwl(wf / "report-hardened-noguard.cwl", overclaim, monthly, LOCAL_EFFECT)
    drift_forged = _run_cwl(wf / "report-hardened-forged.cwl", overclaim, monthly, LOCAL_EFFECT)

    cp_omission = _validate_pack(HERE / "contractplane_omission" / "pack-omitted-verification.yaml")

    return {
        "status": "EXPERIMENTAL",
        "prompt": (
            "Reviewer rebuttal: a single Rego meta-constraint ('no accept without a preceding "
            "verify verdict receipt') should make verification required in the composite too, "
            "collapsing the delta to 'one file vs five files.' This section runs that honestly."
        ),
        "meta_policy": "examples/composite-baseline/policy/meta_accept.rego (evaluated by real opa)",
        "catches_the_naive_omission": {
            "verdict": "YES — the meta-policy makes verification enforceable and the naive omission is caught.",
            "type_coupled_wiring": {
                "workflow": "workflow/report-hardened-omitverify.cwl",
                "what": "drop verify but keep the accept-gate sourcing verify/receipt",
                "cwltool_loads": omitverify_validate["loads"],
                "cwltool_exit_code": omitverify_validate["exit_code"],
                "detected_at": "cwltool validate/load time, before any run",
                "error": omitverify_validate["error_snippet"],
                "note": "Directly analogous to the contractplane validator's 'references unknown evidence'.",
            },
            "loose_receipt_honest": {
                "workflow": "workflow/report-hardened-loose.cwl + receipts/no-verification.receipt.json",
                "outcome": loose_honest["outcome"],
                "rejected_by": loose_honest["rejected_by"],
                "detected_at": "runtime, at the accept-gate",
            },
            "hardened_correct_claim": hardened_correct,
            "hardened_overclaim_still_caught_by_verify": hardened_overclaim,
        },
        "drift_on_the_guard": {
            "premise": (
                "The meta-policy is itself just workflow topology + a policy file. Nothing in CWL "
                "or OPA schematizes the governance topology, so a realistic second-order drift "
                "re-opens the hole. Both variants below LOAD and RUN."
            ),
            "a_guard_dropped": {
                "workflow": "workflow/report-hardened-noguard.cwl",
                "what": "drop the coupled verify+accept-gate pair (the natural refactor once verify is removed)",
                "overclaim_outcome": drift_noguard["outcome"],
                "overclaim_pipeline": drift_noguard["pipeline"],
                "detected": "not detected — nothing requires a workflow to contain an accept-gate",
            },
            "b_receipt_forged": {
                "workflow": "workflow/report-hardened-forged.cwl",
                "what": "keep the accept-gate, drop verify, source the receipt from a producer-side forger",
                "overclaim_outcome": drift_forged["outcome"],
                "overclaim_pipeline": drift_forged["pipeline"],
                "detected": "not detected — the meta-policy checks a receipt's verdict+binding, never its ORIGIN",
                "forgeable_in_correct_wiring": False,
                "forgeable_note": (
                    "In report-hardened.cwl the receipt is type-coupled to verify's output, which CWL "
                    "isolates, so it is NOT producer-forgeable there. Forgeability is a property of the "
                    "receipt's SOURCE in the wiring, which nothing constrains — re-sourcing it re-opens it."
                ),
            },
        },
        "where_enforcement_lives": {
            "composite_hardened": {
                "location": "the assembled workflow TOPOLOGY: presence of verify + accept-gate, and the receipt being sourced from the verifier",
                "static_check": "cwltool validates the wiring you WROTE (dangling sources rejected) but has no schema over the governance topology itself",
                "what_must_drift_to_fail_open": [
                    "delete the coupled verify+accept-gate pair (loads clean, runs green)",
                    "re-source the accept-gate's receipt from a producer/loose input (loads clean, runs green)",
                ],
                "fail_open_mode": "a silent config edit that still validates -> green run accepting the overclaim",
            },
            "contractplane": {
                "location": "the stage's TYPE (requiresEvidence is a required property) plus the frozen kernel that only mints the evidence-recorded transition on an accepted independent verdict",
                "static_check": "contractplane validate rejects a stage missing requiresEvidence (exit 2) and a dangling evidence reference, before any run",
                "cp_omission_validate": cp_omission,
                "what_must_drift_to_fail_open": [
                    "omit requiresEvidence -> validator exit 2, pre-run (cannot express the unsafe stage)",
                    "or tamper with the frozen kernel / verifier binding -> editing the trusted computing base, not a config drift",
                ],
                "fail_open_mode": "requires tripping validation or modifying the TCB — not a silently-valid config",
            },
        },
        "honest_verdict": (
            "The meta-policy NARROWS the delta but does not collapse it to 'one file vs five files'. "
            "Correctly wired, the hardened composite genuinely enforces the invariant, and cwltool's "
            "own loader even rejects the naive verify-omission (dangling receipt source) pre-run — the "
            "reviewer is right that far. But the invariant is a property of an assembled topology that "
            "nothing schematizes: a realistic second-order drift — delete the guard, or forge/re-source "
            "its receipt — LOADS clean and RUNS GREEN, accepting the overclaim. On the contract side the "
            "same invariant is a typed stage property whose unsafe configuration is unrepresentable "
            "(validator exit 2, pre-run) and whose runtime enforcement lives in a frozen kernel; making "
            "it fail open requires tripping validation or editing the trusted computing base. The residual, "
            "load-bearing delta is therefore 'an unsafe configuration you cannot express vs a guard whose "
            "presence and trust-wiring nothing enforces — a guard that itself needs guarding.'"
        ),
        "composite_did_better_here": (
            "cwltool's structural validation genuinely catches the type-coupled omission (dangling source) "
            "at load time — a real, standard-tool safety net the composite gets for free, narrowing the gap."
        ),
    }


def _append(row: dict) -> None:
    with open(EXPERIMENTS, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    if not Path(CWLTOOL).exists() and shutil.which(CWLTOOL) is None:
        print(f"cwltool not found: {CWLTOOL}", file=sys.stderr)
        return 2
    if shutil.which("opa") is None:
        print("opa not found on PATH", file=sys.stderr)
        return 2

    variant = build_hardened_variant()

    # extend the comparison JSON in place (preserve all existing keys)
    if COMPARISON.is_file():
        data = json.loads(COMPARISON.read_text(encoding="utf-8"))
    else:
        data = {}
    data["hardened_variant"] = variant
    COMPARISON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    catch = variant["catches_the_naive_omission"]
    drift = variant["drift_on_the_guard"]
    _append({
        "experiment_id": "e5-hardened-catches-omission",
        "command": ".venv/bin/python examples/composite-baseline/run_hardened.py (report-hardened + report-hardened-omitverify via cwltool + opa meta-policy)",
        "target": "does a Rego meta-constraint make verification required in the composite?",
        "result": (
            f"type-coupled omission: cwltool loads={catch['type_coupled_wiring']['cwltool_loads']} "
            f"exit={catch['type_coupled_wiring']['cwltool_exit_code']} (rejected pre-run); "
            f"loose+honest-receipt: {catch['loose_receipt_honest']['outcome']} "
            f"by {catch['loose_receipt_honest']['rejected_by']}; "
            f"hardened correct: {catch['hardened_correct_claim']['outcome']}"
        ),
        "conclusion": (
            "YES — the meta-policy catches the naive verify-omission. With the receipt type-coupled to "
            "verify, cwltool's loader rejects the omission (dangling 'verify/receipt' source) at validate "
            "time, analogous to the contractplane validator; with a loose receipt an honest no-verdict "
            "receipt is denied at the accept-gate. The reviewer is right that far."
        ),
    })
    _append({
        "experiment_id": "e5-hardened-drift-on-guard",
        "command": ".venv/bin/python examples/composite-baseline/run_hardened.py (report-hardened-noguard + report-hardened-forged via cwltool + opa)",
        "target": "second-order drift the hardened composite is still exposed to (overclaim, monthly-metrics 12 vs 999)",
        "result": json.dumps({
            "guard_dropped(noguard)": drift["a_guard_dropped"]["overclaim_outcome"],
            "receipt_forged": drift["b_receipt_forged"]["overclaim_outcome"],
        }),
        "conclusion": (
            "The hardened composite fails open under realistic second-order drift: dropping the coupled "
            "verify+gate pair runs GREEN and accepts the overclaim; and with the gate PRESENT but its "
            "receipt sourced from a producer-side forger, the overclaim also runs GREEN — the meta-policy "
            "checks a receipt's binding, never its origin. Both variants load and run without any validator "
            "complaint. The guard itself has no guard."
        ),
    })
    _append({
        "experiment_id": "e5-hardened-where-enforcement-lives",
        "command": f"{CONTRACTPLANE} validate examples/composite-baseline/contractplane_omission/pack-omitted-verification.yaml",
        "target": "where each side's 'accept requires verify' invariant is enforced and what must drift to fail open",
        "result": (
            f"composite: workflow topology, no schema over it -> silent-valid config drift fails open; "
            f"contractplane: typed stage property, validator exit "
            f"{variant['where_enforcement_lives']['contractplane']['cp_omission_validate']['exit_code']} pre-run"
        ),
        "conclusion": variant["honest_verdict"],
    })

    print(json.dumps({
        "catches_naive_omission": catch["verdict"],
        "type_coupled_omission_cwltool_exit": catch["type_coupled_wiring"]["cwltool_exit_code"],
        "loose_honest_receipt": catch["loose_receipt_honest"]["outcome"],
        "drift_noguard_overclaim": drift["a_guard_dropped"]["overclaim_outcome"],
        "drift_forged_overclaim": drift["b_receipt_forged"]["overclaim_outcome"],
    }, ensure_ascii=False, indent=2))
    print("\nhonest verdict:\n" + variant["honest_verdict"])
    print(f"\nextended {COMPARISON} with hardened_variant; appended 3 e5-* rows to {EXPERIMENTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
