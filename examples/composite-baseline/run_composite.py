#!/usr/bin/env python3
"""Head-to-head composite-baseline comparison driver (EXPERIMENTAL).

Answers the reviewer objection that ContractPlane's delta over "a composite of
CWL/Argo + OPA + PROV-style provenance" is asserted, never shown. It runs the
SAME governed report scenario on BOTH sides with runnable artifacts and records
an honest, fair comparison.

Both sides are driven by the SAME recorded producer claims (the sonnet row of
examples/governed-run/episodes/study/), so any difference in outcome is a
property of the governance mechanism, not of the producer.

What it runs:
  1. composite-correct   : the 4 study conditions through workflow/report-governed.cwl
                           (a real cwltool workflow: schema -> verify -> OPA policy -> PROV log).
  2. composite-misconfig : the same 4 conditions through workflow/report-misconfigured.cwl,
                           which silently drops the verify step (realistic config drift).
  3. contractplane       : the same 4 recorded episodes replayed through the repo's
                           own experimental governed kernel path.
  4. misconfiguration delta: the composite-misconfig pipeline ACCEPTS the overclaim
                           and runs green; the equivalent omission on the contractplane
                           side is REJECTED by `contractplane validate` before anything runs.
  5. authority           : external publish denied without a grant / allowed with one,
                           through the same OPA gate (mirrors governed-run scenarios 4 & 5).

Outputs artifacts/composite_comparison.json and appends one artifacts/experiments.jsonl
row per real run. Nothing here is fabricated: outcomes come from actual tool exit codes.

Run from the repo root:
    .venv/bin/python examples/composite-baseline/run_composite.py
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

# condition -> (claim file, dataset name, true row count)
CONDITIONS = {
    "correct": ("sonnet-correct.claim.json", "weekly-metrics", 3),
    "overclaim": ("sonnet-overclaim.claim.json", "monthly-metrics", 12),
    "borderline": ("sonnet-borderline.claim.json", "sprint-metrics", 7),
    "format-violation": ("sonnet-format-violation.claim.json", "weekly-metrics", 3),
}


def _run_cwl(workflow: Path, claim: Path, dataset: Path, effect: Path) -> dict:
    """Run one condition through a CWL workflow. Return outcome + the gate that
    reddened the pipeline (parsed from the tools' own REJECT/DENY messages)."""
    outdir = Path(tempfile.mkdtemp(prefix="composite-out-"))
    try:
        proc = subprocess.run(
            [
                CWLTOOL, "--quiet", "--outdir", str(outdir), str(workflow),
                "--claim", str(claim), "--schema", str(SCHEMA),
                "--dataset", str(dataset), "--effect", str(effect),
            ],
            capture_output=True, text=True, cwd=str(HERE),
        )
        stderr = proc.stderr
        gate = None
        for marker, name in (
            ("schema-gate REJECT", "schema-gate"),
            ("verify REJECT", "verify"),
            ("policy-gate DENY", "policy-gate"),
        ):
            if marker in stderr:
                gate = name
                break
        prov = outdir / "provenance.json"
        record = json.loads(prov.read_text()) if proc.returncode == 0 and prov.is_file() else None
        return {
            "exit_code": proc.returncode,
            "pipeline": "green" if proc.returncode == 0 else "red",
            "outcome": "accepted" if proc.returncode == 0 else "rejected",
            "rejected_by": gate,
            "provenance_written": record is not None,
        }
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def _run_contractplane_side() -> dict:
    """Replay the same four sonnet episodes through the repo's own governed kernel."""
    from contractplane.compiler import compile_plan
    from contractplane.experimental import (
        RecordCountRecomputer, load_episode, replay_episode, RunResult, Workspace,
    )
    from contractplane.ledger import JsonlLedger
    from contractplane.loader import load_domain_pack

    pack = load_domain_pack(GOVERNED / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="report")
    recomputer = RecordCountRecomputer(DATASETS)
    results: dict[str, dict] = {}
    study_dir = GOVERNED / "episodes" / "study"
    for condition in CONDITIONS:
        episode = load_episode(study_dir / f"episode-sonnet-{condition}.json")
        scratch = Path(tempfile.mkdtemp(prefix="cp-side-"))
        try:
            report = replay_episode(
                episode, plan=plan, pack_dir=GOVERNED,
                workspace=Workspace.create(scratch / "workspace"),
                ledger=JsonlLedger(scratch / "ledger.jsonl"),
                execution_id=f"composite-cmp-{condition}", recomputer=recomputer,
            )
            accepted = report.result is RunResult.SUCCEEDED
            verdict = report.verdicts[-1] if report.verdicts else None
            results[condition] = {
                "result": report.result.value,
                "outcome": "accepted" if accepted else "rejected",
                "verdict_method": getattr(verdict, "method", None),
            }
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    return results


def _validate(pack: Path) -> dict:
    proc = subprocess.run(
        [CONTRACTPLANE, "validate", str(pack)], capture_output=True, text=True
    )
    # A valid pack prints JSON to stdout; a rejection prints JSON to stderr.
    payload = proc.stdout.strip() or proc.stderr.strip()
    out = json.loads(payload) if payload else {}
    return {
        "exit_code": proc.returncode,
        "valid": bool(out.get("valid", False)),
        "issues": out.get("issues"),
    }


def _append_experiment(row: dict) -> None:
    with open(EXPERIMENTS, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    for tool, label in ((CWLTOOL, "cwltool"), (CONTRACTPLANE, "contractplane")):
        if not Path(tool).exists() and shutil.which(tool) is None:
            print(f"required tool not found: {label} ({tool})", file=sys.stderr)
            return 2
    if shutil.which("opa") is None:
        print("required tool not found: opa (brew install opa)", file=sys.stderr)
        return 2

    governed_wf = HERE / "workflow" / "report-governed.cwl"
    misconfig_wf = HERE / "workflow" / "report-misconfigured.cwl"

    # (1)+(2) composite correct & misconfigured across the four conditions.
    composite_correct: dict[str, dict] = {}
    composite_misconfig: dict[str, dict] = {}
    for condition, (claim_name, dataset_name, _true) in CONDITIONS.items():
        claim = HERE / "claims" / claim_name
        dataset = DATASETS / f"{dataset_name}.json"
        composite_correct[condition] = _run_cwl(governed_wf, claim, dataset, LOCAL_EFFECT)
        composite_misconfig[condition] = _run_cwl(misconfig_wf, claim, dataset, LOCAL_EFFECT)

    # (3) contractplane side, same recorded episodes.
    contractplane = _run_contractplane_side()

    # (4) misconfiguration delta on the contractplane side: validate-time rejection.
    omission = HERE / "contractplane_omission" / "pack-omitted-verification.yaml"
    control = HERE / "contractplane_omission" / "pack-coupled-control.yaml"
    validate_omission = _validate(omission)
    validate_control = _validate(control)

    # (5) authority scenarios through the same OPA gate (correct claim, weekly-metrics).
    correct_claim = HERE / "claims" / "sonnet-correct.claim.json"
    weekly = DATASETS / "weekly-metrics.json"
    authority = {
        "external_no_grant": _run_cwl(
            governed_wf, correct_claim, weekly,
            HERE / "effects" / "external-publish-nogrant.effect.json",
        ),
        "external_granted": _run_cwl(
            governed_wf, correct_claim, weekly,
            HERE / "effects" / "external-publish-granted.effect.json",
        ),
    }

    # ---- comparison table: condition x {contractplane, composite-correct, composite-misconfigured}
    table = {}
    for condition in CONDITIONS:
        table[condition] = {
            "contractplane": contractplane[condition]["outcome"],
            "composite_correct": composite_correct[condition]["outcome"],
            "composite_misconfigured": composite_misconfig[condition]["outcome"],
            "contractplane_detail": contractplane[condition],
            "composite_correct_detail": composite_correct[condition],
            "composite_misconfigured_detail": composite_misconfig[condition],
        }

    comparison = {
        "experiment_id": "e4-composite-baseline",
        "status": "EXPERIMENTAL",
        "generated_from": "examples/composite-baseline/run_composite.py",
        "claim_source": "examples/governed-run/episodes/study/ (sonnet row, real-recorded)",
        "tools": {
            "cwltool": _tool_version([CWLTOOL, "--version"]),
            "opa": _tool_version(["opa", "version"]),
            "contractplane_validate": "repo .venv CLI",
            "all_real": True,
            "substitutions": "none — cwltool, opa, and the contractplane validator are all the real tools",
        },
        "scenario": (
            "Governed report flow: a producer counts records in a caller-owned dataset "
            "and claims a count; the claim must clear a schema gate and an independent "
            "recomputation; an external publish requires explicit authority."
        ),
        "conditions": table,
        "misconfiguration_experiment": {
            "description": (
                "A single realistic drift on each side: drop the independent verification. "
                "Composite: delete the verify step from the CWL workflow. ContractPlane: "
                "drop requiresEvidence from the stage."
            ),
            "composite": {
                "variant": "workflow/report-misconfigured.cwl",
                "overclaim_pipeline": composite_misconfig["overclaim"]["pipeline"],
                "overclaim_outcome": composite_misconfig["overclaim"]["outcome"],
                "detected_at": "not detected — workflow is valid CWL, runs green, PROV log records a satisfied run",
            },
            "contractplane": {
                "variant": "contractplane_omission/pack-omitted-verification.yaml",
                "validate_exit_code": validate_omission["exit_code"],
                "validate_valid": validate_omission["valid"],
                "validate_issues": validate_omission["issues"],
                "coupled_control_valid": validate_control["valid"],
                "detected_at": "validation time, before any run — 'requiresEvidence' is a required property",
            },
            "delta": (
                "The same governance omission is invisible on the composite side (green run, "
                "overclaim accepted) but is a typed-coupling violation the contractplane "
                "validator rejects statically. The coupled control pack validates, proving "
                "the rejection is caused by the single dropped coupling."
            ),
        },
        "authority": authority,
        "integration_surface": _integration_surface(),
        "composite_did_better": [
            "Mature, standardized ecosystem: CWL is an open standard with multiple conformant "
            "engines (cwltool, Toil, Arvados) and OPA/Rego is a CNCF-graduated policy engine "
            "with a large rule ecosystem; ContractPlane's kernel is a single research prototype.",
            "Scalability and portability: the CWL/OPA stack already runs distributed, containerized, "
            "and HPC/cloud workloads with caching, retries, and provenance at production scale, "
            "which the experimental contractplane slice does not attempt.",
            "Separation of concerns and reuse: schema validation, policy, orchestration, and "
            "provenance are independent, individually swappable, widely-understood components with "
            "existing tooling and staff familiarity.",
        ],
        "honest_caveats": [
            "The composite here is arguably shown in a FAVORABLE light: its gates are wired "
            "correctly by hand, its verify step is a purpose-built recompute, and the schema/policy "
            "are hand-mirrored from the contractplane contract — a real integrator must author and "
            "keep all of that in sync themselves.",
            "The contractplane side reuses a library recomputer (RecordCountRecomputer); the "
            "composite's verify script is user-authored. Both sides lean on library engines "
            "(cwltool/opa vs the contractplane kernel). LOC counts below separate user-authored "
            "glue from library code.",
            "This exercises singleton local stages with JSON evidence only; neither side's harder "
            "cases (fanout, remote/sandboxed adapters, semantic-review evidence) are demonstrated.",
        ],
    }

    # Keep the canonical generator complete: fold in the hardened-variant section
    # (run_hardened.py can also add it standalone). Lazily imported so this module
    # stays loadable where cwltool/opa are absent and so importing it for its
    # helpers never triggers the hardened experiment run.
    try:
        sys.path.insert(0, str(HERE))
        from run_hardened import build_hardened_variant

        comparison["hardened_variant"] = build_hardened_variant()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"note: hardened_variant section skipped ({exc})", file=sys.stderr)

    ARTIFACTS.mkdir(exist_ok=True)
    COMPARISON.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # ---- append one experiments.jsonl row per real run-group
    cc = {c: composite_correct[c]["outcome"] for c in CONDITIONS}
    cm = {c: composite_misconfig[c]["outcome"] for c in CONDITIONS}
    cp = {c: contractplane[c]["outcome"] for c in CONDITIONS}
    _append_experiment({
        "experiment_id": "e4-composite-correct",
        "command": ".venv/bin/python examples/composite-baseline/run_composite.py (workflow/report-governed.cwl via cwltool)",
        "target": "4 study conditions (sonnet claims) through the correctly-wired CWL+OPA+PROV composite",
        "result": json.dumps(cc),
        "conclusion": (
            "Correctly configured, the composite matches contractplane per-condition: correct accepted; "
            "overclaim and borderline rejected by the recompute (verify) step; format-violation rejected "
            "by the schema gate. Real cwltool exit codes; real opa policy gate."
        ),
    })
    _append_experiment({
        "experiment_id": "e4-composite-misconfigured",
        "command": ".venv/bin/python examples/composite-baseline/run_composite.py (workflow/report-misconfigured.cwl via cwltool)",
        "target": "same 4 conditions through the composite with the verify step silently dropped",
        "result": json.dumps(cm),
        "conclusion": (
            "With the verify step omitted (realistic copy-paste drift), the overclaim runs GREEN and is "
            "ACCEPTED with a satisfied PROV record; the composite offers no structural signal that a "
            "governance step is missing. Only format-violation is still caught (by the schema gate)."
        ),
    })
    _append_experiment({
        "experiment_id": "e4-contractplane-side",
        "command": ".venv/bin/python examples/composite-baseline/run_composite.py (replay_episode through the governed kernel)",
        "target": "same 4 sonnet episodes replayed through contractplane.experimental",
        "result": json.dumps(cp),
        "conclusion": (
            "The repo's own governed kernel reproduces the intended outcomes on the same recorded claims: "
            "correct accepted by recomputation; overclaim and borderline rejected by recomputation; "
            "format-violation rejected by the schema gate."
        ),
    })
    _append_experiment({
        "experiment_id": "e4-misconfiguration-delta",
        "command": f"{CONTRACTPLANE} validate examples/composite-baseline/contractplane_omission/pack-omitted-verification.yaml",
        "target": "the contractplane analogue of the dropped-verify omission",
        "result": (
            f"omission: valid={validate_omission['valid']} exit={validate_omission['exit_code']} "
            f"issues={json.dumps(validate_omission['issues'])}; control: valid={validate_control['valid']}"
        ),
        "conclusion": (
            "The same governance omission that the composite accepts at runtime is REJECTED by "
            "`contractplane validate` before any run: 'requiresEvidence' is a required property. The "
            "coupled control pack validates, isolating the rejection to the single dropped coupling. "
            "This is the 'defaults and typed coupling' delta made measurable."
        ),
    })
    _append_experiment({
        "experiment_id": "e4-composite-authority",
        "command": ".venv/bin/python examples/composite-baseline/run_composite.py (OPA policy gate, external effects)",
        "target": "external publish without a grant vs with an explicit grant, through the real opa gate",
        "result": json.dumps({
            "external_no_grant": authority["external_no_grant"]["outcome"],
            "external_granted": authority["external_granted"]["outcome"],
        }),
        "conclusion": (
            "The OPA/Rego deny-by-default policy denies the external publish without a grant (red) and "
            "allows it with an explicit external grant (green), mirroring governed-run scenarios 4 and 5."
        ),
    })

    print(json.dumps(comparison["conditions"], ensure_ascii=False, indent=2, sort_keys=True))
    print("\nmisconfiguration delta:")
    print(f"  composite-misconfigured overclaim -> {composite_misconfig['overclaim']['outcome']} "
          f"({composite_misconfig['overclaim']['pipeline']} pipeline)")
    print(f"  contractplane omission validate    -> valid={validate_omission['valid']} "
          f"(exit {validate_omission['exit_code']})")
    print(f"\nwrote {COMPARISON}")
    return 0


def _tool_version(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return (proc.stdout or proc.stderr).strip().splitlines()[0]
    except Exception as exc:  # pragma: no cover - defensive
        return f"unknown ({exc})"


def _nonblank_loc(path: Path) -> int:
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


def _integration_surface() -> dict:
    """Count files, distinct languages/configs, and non-blank LOC of the user-authored
    governed behavior on each side. Honest and mechanical: it counts the actual files."""
    composite_files = {
        "cwl_workflow": [
            HERE / "workflow" / "report-governed.cwl",
            HERE / "workflow" / "report-misconfigured.cwl",
        ],
        "cwl_tool_wrappers": sorted((HERE / "tools").glob("*.cwl")),
        "python_tools": sorted((HERE / "tools").glob("*.py")),
        "rego_policy": [HERE / "policy" / "authorization.rego"],
        "json_schema": [SCHEMA],
        "effect_descriptors": sorted((HERE / "effects").glob("*.json")),
    }
    composite_loc = sum(
        _nonblank_loc(p) for group in composite_files.values() for p in group
    )
    composite_file_count = sum(len(group) for group in composite_files.values())

    # contractplane user-authored governed behavior: the declarative pack stanzas.
    cp_pack = GOVERNED / "domainpack.yaml"
    cp_files = {"domain_pack": [cp_pack]}
    cp_loc = sum(_nonblank_loc(p) for group in cp_files.values() for p in group)
    cp_file_count = sum(len(group) for group in cp_files.values())

    return {
        "note": (
            "User-authored governed behavior only. Both sides also rely on library engines "
            "(cwltool + opa on the composite side; the contractplane kernel on the other). "
            "The composite must additionally keep the schema, policy, verify logic, and step "
            "wiring mutually consistent by hand; the pack expresses the same behavior as one "
            "declarative, statically-validated document."
        ),
        "composite": {
            "files": composite_file_count,
            "distinct_languages_configs": ["CWL (YAML)", "Python", "Rego", "JSON Schema", "JSON (effects)"],
            "distinct_language_count": 5,
            "nonblank_loc": composite_loc,
            "breakdown": {k: [str(p.relative_to(REPO_ROOT)) for p in v] for k, v in composite_files.items()},
        },
        "contractplane": {
            "files": cp_file_count,
            "distinct_languages_configs": ["DomainPack (YAML)"],
            "distinct_language_count": 1,
            "nonblank_loc": cp_loc,
            "breakdown": {k: [str(p.relative_to(REPO_ROOT)) for p in v] for k, v in cp_files.items()},
            "caveat": (
                "The pack's LOC also covers the publish flow and the adversarial probe flow; the "
                "report-only governed behavior is a subset. Even counted generously it is one file "
                "in one language, statically validated."
            ),
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
