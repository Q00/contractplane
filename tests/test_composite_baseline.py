"""Tests for the EXPERIMENTAL composite-baseline head-to-head comparison.

These pin the reviewer-facing claims of examples/composite-baseline/: the
correctly-wired CWL+OPA+PROV composite reproduces the per-condition governance
outcomes, but a single realistic omission (dropping the verify step) makes the
composite ACCEPT an overclaim at runtime, while the equivalent omission on the
contractplane side is REJECTED by the validator before anything runs.

The cwltool-driven cases are skipped when the composite cwltool venv or the opa
binary is unavailable, so the rest of the suite is unaffected on bare machines.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = REPO_ROOT / "examples" / "composite-baseline"
CWLTOOL = REPO_ROOT / ".ouroboros" / "composite-venv" / "bin" / "cwltool"
CONTRACTPLANE = REPO_ROOT / ".venv" / "bin" / "contractplane"
DATASETS = REPO_ROOT / "examples" / "governed-run" / "datasets"
SCHEMA = BASE / "schema" / "report-artifact.schema.json"
LOCAL_EFFECT = BASE / "effects" / "local-report.effect.json"

_cwl_missing = not CWLTOOL.exists() or shutil.which("opa") is None
requires_composite = pytest.mark.skipif(
    _cwl_missing, reason="composite cwltool venv or opa binary unavailable"
)


def _load_driver():
    spec = importlib.util.spec_from_file_location(
        "composite_driver", BASE / "run_composite.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(workflow_name: str, claim_name: str, dataset_name: str, effect: Path = LOCAL_EFFECT) -> dict:
    driver = _load_driver()
    return driver._run_cwl(
        BASE / "workflow" / workflow_name,
        BASE / "claims" / claim_name,
        DATASETS / f"{dataset_name}.json",
        effect,
    )


# ---- (1) the correctly-configured composite reproduces the governance outcomes


@requires_composite
def test_composite_correct_accepts_true_claim():
    result = _run("report-governed.cwl", "sonnet-correct.claim.json", "weekly-metrics")
    assert result["outcome"] == "accepted"
    assert result["pipeline"] == "green"
    assert result["provenance_written"] is True


@requires_composite
def test_composite_correct_rejects_overclaim_at_verify():
    result = _run("report-governed.cwl", "sonnet-overclaim.claim.json", "monthly-metrics")
    assert result["outcome"] == "rejected"
    assert result["rejected_by"] == "verify"


@requires_composite
def test_composite_correct_rejects_borderline_at_verify():
    result = _run("report-governed.cwl", "sonnet-borderline.claim.json", "sprint-metrics")
    assert result["outcome"] == "rejected"
    assert result["rejected_by"] == "verify"


@requires_composite
def test_composite_correct_rejects_format_violation_at_schema_gate():
    result = _run("report-governed.cwl", "sonnet-format-violation.claim.json", "weekly-metrics")
    assert result["outcome"] == "rejected"
    assert result["rejected_by"] == "schema-gate"


# ---- (2) the misconfiguration delta: the composite accepts the overclaim


@requires_composite
def test_composite_misconfigured_accepts_overclaim():
    """The load-bearing delta: with the verify step dropped, the overclaim runs
    green and is accepted with a satisfied PROV record."""
    result = _run("report-misconfigured.cwl", "sonnet-overclaim.claim.json", "monthly-metrics")
    assert result["outcome"] == "accepted"
    assert result["pipeline"] == "green"
    assert result["provenance_written"] is True


@requires_composite
def test_composite_misconfigured_still_catches_format_violation():
    """The schema gate survives the omission, so format-violation is still red —
    the omission specifically defeats recomputation, not every gate."""
    result = _run("report-misconfigured.cwl", "sonnet-format-violation.claim.json", "weekly-metrics")
    assert result["outcome"] == "rejected"
    assert result["rejected_by"] == "schema-gate"


@requires_composite
def test_composite_policy_gate_denies_external_without_grant():
    result = _run(
        "report-governed.cwl", "sonnet-correct.claim.json", "weekly-metrics",
        BASE / "effects" / "external-publish-nogrant.effect.json",
    )
    assert result["outcome"] == "rejected"
    assert result["rejected_by"] == "policy-gate"


@requires_composite
def test_composite_policy_gate_allows_external_with_grant():
    result = _run(
        "report-governed.cwl", "sonnet-correct.claim.json", "weekly-metrics",
        BASE / "effects" / "external-publish-granted.effect.json",
    )
    assert result["outcome"] == "accepted"


# ---- (3) the contractplane-side omission is rejected at validation time


def _validate(pack: Path) -> dict:
    proc = subprocess.run(
        [str(CONTRACTPLANE), "validate", str(pack)], capture_output=True, text=True
    )
    payload = proc.stdout.strip() or proc.stderr.strip()
    return {"exit": proc.returncode, "out": json.loads(payload)}


@pytest.mark.skipif(not CONTRACTPLANE.exists(), reason="contractplane CLI unavailable")
def test_contractplane_omission_rejected_by_validator():
    result = _validate(BASE / "contractplane_omission" / "pack-omitted-verification.yaml")
    assert result["out"]["valid"] is False
    messages = " ".join(i["message"] for i in result["out"]["issues"])
    assert "requiresEvidence" in messages


@pytest.mark.skipif(not CONTRACTPLANE.exists(), reason="contractplane CLI unavailable")
def test_contractplane_coupled_control_validates():
    """Isolates the rejection to the single dropped coupling: the otherwise
    identical pack that keeps requiresEvidence validates."""
    result = _validate(BASE / "contractplane_omission" / "pack-coupled-control.yaml")
    assert result["out"]["valid"] is True


# ---- (4) the comparison artifact is well-formed


def test_comparison_json_is_well_formed_when_present():
    path = REPO_ROOT / "artifacts" / "composite_comparison.json"
    if not path.is_file():
        pytest.skip("composite_comparison.json not generated in this checkout")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("conditions", "misconfiguration_experiment", "integration_surface", "composite_did_better"):
        assert key in data, key
    # the pinned delta must be recorded in the artifact
    assert data["conditions"]["overclaim"]["composite_correct"] == "rejected"
    assert data["conditions"]["overclaim"]["composite_misconfigured"] == "accepted"
    assert data["conditions"]["overclaim"]["contractplane"] == "rejected"
    surface = data["integration_surface"]
    assert surface["composite"]["distinct_language_count"] >= surface["contractplane"]["distinct_language_count"]


# ---- (5) the HARDENED variant: the meta-policy rebuttal, run honestly


def _load_hardened():
    spec = importlib.util.spec_from_file_location(
        "hardened_driver", BASE / "run_hardened.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_hardened(workflow_name: str, claim_name: str, dataset_name: str, extra=None) -> dict:
    h = _load_hardened()
    return h._run_cwl(
        BASE / "workflow" / workflow_name,
        BASE / "claims" / claim_name,
        DATASETS / f"{dataset_name}.json",
        LOCAL_EFFECT,
        extra,
    )


@requires_composite
def test_hardened_accepts_correct_claim():
    result = _run_hardened("report-hardened.cwl", "sonnet-correct.claim.json", "weekly-metrics")
    assert result["outcome"] == "accepted"
    assert result["pipeline"] == "green"


@requires_composite
def test_hardened_overclaim_still_caught_by_verify():
    result = _run_hardened("report-hardened.cwl", "sonnet-overclaim.claim.json", "monthly-metrics")
    assert result["outcome"] == "rejected"
    assert result["rejected_by"] == "verify"


@requires_composite
def test_hardened_naive_omission_rejected_by_cwltool_loader():
    """The reviewer's point, vindicated: dropping verify while the accept-gate is
    type-coupled to its receipt makes cwltool's own loader refuse the workflow —
    caught at validate time, before any run (analogous to the pack validator)."""
    h = _load_hardened()
    result = h._validate_cwl(BASE / "workflow" / "report-hardened-omitverify.cwl")
    assert result["loads"] is False
    assert result["exit_code"] != 0


@requires_composite
def test_hardened_loose_honest_receipt_denied_at_accept_gate():
    result = _run_hardened(
        "report-hardened-loose.cwl", "sonnet-overclaim.claim.json", "monthly-metrics",
        ["--receipt", str(BASE / "receipts" / "no-verification.receipt.json")],
    )
    assert result["outcome"] == "rejected"


@requires_composite
def test_hardened_drift_noguard_accepts_overclaim():
    """Drift-on-the-guard (a): drop the coupled verify+gate pair -> green overclaim."""
    result = _run_hardened("report-hardened-noguard.cwl", "sonnet-overclaim.claim.json", "monthly-metrics")
    assert result["outcome"] == "accepted"
    assert result["pipeline"] == "green"


@requires_composite
def test_hardened_drift_forged_receipt_accepts_overclaim():
    """Drift-on-the-guard (b): guard PRESENT and consulted, but a producer-forged
    receipt satisfies it -> green overclaim. The meta-policy checks binding, not origin."""
    result = _run_hardened("report-hardened-forged.cwl", "sonnet-overclaim.claim.json", "monthly-metrics")
    assert result["outcome"] == "accepted"
    assert result["pipeline"] == "green"


def test_hardened_variant_section_well_formed_when_present():
    path = REPO_ROOT / "artifacts" / "composite_comparison.json"
    if not path.is_file():
        pytest.skip("composite_comparison.json not generated in this checkout")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "hardened_variant" not in data:
        pytest.skip("hardened_variant not generated in this checkout")
    hv = data["hardened_variant"]
    for key in ("catches_the_naive_omission", "drift_on_the_guard", "where_enforcement_lives", "honest_verdict"):
        assert key in hv, key
    # the pinned findings: naive omission caught, but both drifts fail open
    assert hv["catches_the_naive_omission"]["type_coupled_wiring"]["cwltool_loads"] is False
    assert hv["drift_on_the_guard"]["a_guard_dropped"]["overclaim_outcome"] == "accepted"
    assert hv["drift_on_the_guard"]["b_receipt_forged"]["overclaim_outcome"] == "accepted"
    # task-1 keys must survive the extension
    assert "conditions" in data and "misconfiguration_experiment" in data


# ---- (6) Guardrails AI baseline: runtime structural output validator


ISOLATED_PY = REPO_ROOT / ".ouroboros" / "composite-venv" / "bin" / "python"
GUARD_CLI = BASE / "guardrails" / "report_guard.py"


def _guardrails_available() -> bool:
    if not ISOLATED_PY.exists():
        return False
    proc = subprocess.run(
        [str(ISOLATED_PY), "-c", "import guardrails"], capture_output=True, text=True
    )
    return proc.returncode == 0


requires_guardrails = pytest.mark.skipif(
    not _guardrails_available(),
    reason="guardrails-ai not installed in the isolated composite venv",
)


def _run_guard(artifacts_by_id: dict) -> dict:
    """Invoke the Guard under the isolated venv; return {id: passed_bool}."""
    payload = [{"id": k, "artifact": v} for k, v in artifacts_by_id.items()]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        tmp = fh.name
    try:
        proc = subprocess.run(
            [str(ISOLATED_PY), str(GUARD_CLI), tmp], capture_output=True, text=True
        )
        assert proc.returncode == 0, proc.stderr
        return {r["id"]: r["guard_passed"] for r in json.loads(proc.stdout)}
    finally:
        os.unlink(tmp)


@requires_guardrails
def test_guardrails_accepts_schema_valid_wrong_numbers():
    """The load-bearing finding: a structural Guard accepts schema-valid claims
    even when the number is wrong (an overclaim and an off-by-one both pass)."""
    results = _run_guard({
        "correct": {"dataset": "weekly-metrics", "rows": 3, "generatedBy": "compile-report"},
        "overclaim": {"dataset": "monthly-metrics", "rows": 999, "generatedBy": "compile-report"},
        "offbyone": {"dataset": "hard-count-g", "rows": 753, "generatedBy": "compile-report"},
    })
    assert results["correct"] is True
    assert results["overclaim"] is True  # schema-valid, wrong number -> guard cannot catch
    assert results["offbyone"] is True   # off-by-one near-miss -> guard cannot catch


@requires_guardrails
def test_guardrails_rejects_format_violation():
    """A missing required field IS a structural defect, so the Guard catches it."""
    results = _run_guard({
        "format-violation": {"dataset": "weekly-metrics", "rows": 3},
        "rows-zero": {"dataset": "weekly-metrics", "rows": 0, "generatedBy": "compile-report"},
    })
    assert results["format-violation"] is False
    assert results["rows-zero"] is False  # violates rows >= 1


def test_guardrails_comparison_json_well_formed_when_present():
    path = REPO_ROOT / "artifacts" / "guardrails_comparison.json"
    if not path.is_file():
        pytest.skip("guardrails_comparison.json not generated in this checkout")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("per_claim", "summary", "finding", "guardrails_did_better"):
        assert key in data, key
    s = data["summary"]
    # the pinned delta: structure catches 0 numeric errors; recomputation catches all 4
    assert s["guardrails_natural_errors_caught"] == "0/4"
    assert s["recomputation_natural_errors_caught"] == "4/4"
    assert s["guardrails_offbyone_caught"] == "0/3"
    assert s["recomputation_offbyone_caught"] == "3/3"
    # both structural validators catch every format violation; neither over-rejects correct claims
    assert s["guardrails_format_violations_caught"] == "3/3"
    assert s["guardrails_false_rejections_on_correct"] == "0/5"
    assert len(data["per_claim"]) == 12
