"""Tests for the experimental ACP second substrate.

EXPERIMENTAL — covers contractplane.experimental.acp_adapter (real ACP session
against the Node agent built on the official SDK) and
contractplane.experimental.substrate (cross-substrate governed study). The ACP
tests are skipped with a clear reason if Node / the SDK are unavailable; in this
repo they are installed, so they run.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from contractplane.experimental import (
    acp_available,
    run_acp_task,
    run_substrate_study,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
DATASETS_DIR = PACK_DIR / "datasets"

_available, _reason = acp_available()
acp_required = pytest.mark.skipif(not _available, reason=f"ACP unavailable: {_reason}")


def _echo_task(target: Path, rows: int) -> dict:
    return {
        "mode": "echo",
        "action": {"title": "compile report", "capability": "compile-report", "sideEffects": "local"},
        "evidenceTargets": {"report-artifact": str(target)},
        "claim": {
            "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": rows},
            "artifact": {"report-artifact": {"dataset": "weekly-metrics", "rows": rows, "generatedBy": "compile-report"}},
        },
    }


@acp_required
def test_acp_session_allow_produces_claim_over_real_acp(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / "evidence").mkdir(parents=True)
    target = workspace / "evidence" / "compile.report-artifact.json"
    result = run_acp_task(_echo_task(target, 3), allow=True, cwd=workspace)
    assert result.permission_requested is True  # a real session/request_permission happened
    assert result.protocol_version == 1
    assert result.stop_reason == "end_turn"
    assert result.outputs == {"artifact": "evidence/compile.report-artifact.json", "rows": 3}
    assert target.is_file()


@acp_required
def test_acp_session_deny_performs_no_work(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / "evidence").mkdir(parents=True)
    target = workspace / "evidence" / "compile.report-artifact.json"
    result = run_acp_task(_echo_task(target, 3), allow=False, cwd=workspace)
    assert result.permission_requested is True
    assert result.stop_reason == "refusal"
    assert result.outputs is None
    assert not target.is_file()  # deny over ACP -> the agent wrote nothing


@acp_required
def test_acp_worker_mode_shells_out_to_the_python_worker(tmp_path: Path) -> None:
    import json

    workspace = tmp_path / "ws"
    (workspace / "evidence").mkdir(parents=True)
    (workspace / "_dispatch").mkdir(parents=True)
    target = workspace / "evidence" / "compile.report-artifact.json"
    assignment = workspace / "_dispatch" / "compile.json"
    assignment.write_text(
        json.dumps(
            {
                "stage": "compile",
                "input": {"dataset": "weekly-metrics"},
                "evidenceTargets": {"report-artifact": str(target)},
            }
        )
    )
    task = {
        "mode": "worker",
        "action": {"title": "compile", "capability": "compile-report", "sideEffects": "local"},
        "python": sys.executable,
        "worker": str(PACK_DIR / "workers" / "compile_report.py"),
        "assignmentPath": str(assignment),
        "cwd": str(workspace),
    }
    result = run_acp_task(task, allow=True, cwd=workspace)
    assert result.outputs["rows"] == 3  # the real worker counted weekly-metrics
    assert target.is_file()


@acp_required
def test_cross_substrate_outcomes_are_identical() -> None:
    report = run_substrate_study(pack_dir=PACK_DIR, datasets_dir=DATASETS_DIR, python=sys.executable)
    assert report["acpAvailable"] is True
    # Every condition yields the same governed outcome on both substrates.
    assert report["agreementCount"] == report["conditionsCount"] == 5
    for name, agreement in report["agreement"].items():
        assert agreement["agree"], (name, agreement)
    expected = {
        "correct": "accepted",
        "overclaim": "rejected",
        "borderline": "rejected",
        "authority-denied": "denied",
        "authority-granted": "accepted",
    }
    assert report["table"]["local-process"] == expected
    assert report["table"]["acp"] == expected


@acp_required
def test_authority_denial_happens_over_real_acp_messages() -> None:
    report = run_substrate_study(pack_dir=PACK_DIR, datasets_dir=DATASETS_DIR, python=sys.executable)
    acp_deny = next(
        r for r in report["rows"] if r["substrate"] == "acp" and r["condition"] == "authority-denied"
    )
    assert acp_deny["outcome"] == "denied"
    assert acp_deny["permissionRequested"] is True
    assert acp_deny["permissionAnswer"] == "deny"
    assert acp_deny["permissionChannel"] == "acp:session/request_permission"
    assert acp_deny["acpStopReason"] == "refusal"


def test_acp_availability_reports_a_reason() -> None:
    available, reason = acp_available()
    assert isinstance(available, bool)
    assert isinstance(reason, str) and reason