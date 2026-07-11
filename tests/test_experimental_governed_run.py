"""Tests for the experimental end-to-end governed execution slice.

EXPERIMENTAL — covers contractplane.experimental (adapter, authority gate,
recomputation-based independent verifier, the governed-run harness, and the LLM
producer-episode replay harness), all driving the frozen kernel.
"""

from __future__ import annotations

from pathlib import Path

import json

import pytest

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    AuthorityGate,
    AuthorityGrant,
    ChainRecomputer,
    ConfigurationError,
    EpisodeError,
    FilterCountRecomputer,
    GovernedRunner,
    IndependentVerifier,
    RecordCountRecomputer,
    RunResult,
    SumRecomputer,
    Workspace,
    load_episode,
    parse_episode,
    replay_episode,
)
from contractplane.ledger import JsonlLedger
from contractplane.loader import load_domain_pack, parse_domain_pack
from contractplane.state import ExecutionMachine, ExecutionStatus, StageStatus, UnitRef

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
EPISODES_DIR = PACK_DIR / "episodes"
REPORT_PLAN = compile_plan(PACK, entrypoint_id="report")
PUBLISH_PLAN = compile_plan(PACK, entrypoint_id="publish")
FABRICATED_PLAN = compile_plan(PACK, entrypoint_id="report-fabricated")
AGGREGATE_PLAN = compile_plan(PACK, entrypoint_id="aggregate")
FILTER_PLAN = compile_plan(PACK, entrypoint_id="filter-count")


def _chain() -> ChainRecomputer:
    return ChainRecomputer(
        [
            RecordCountRecomputer(DATASETS_DIR),
            SumRecomputer(DATASETS_DIR),
            FilterCountRecomputer(DATASETS_DIR),
        ]
    )


def _recomputer() -> RecordCountRecomputer:
    return RecordCountRecomputer(DATASETS_DIR)


def _runner(
    tmp_path: Path,
    plan,
    *,
    grant: AuthorityGrant | None = None,
    ledger: JsonlLedger | None = None,
) -> GovernedRunner:
    return GovernedRunner(
        plan,
        pack_dir=PACK_DIR,
        workspace=Workspace.create(tmp_path / "workspace"),
        ledger=ledger or JsonlLedger(tmp_path / "ledger.jsonl"),
        authority=AuthorityGate(grant),
        recomputer=_recomputer(),
    )


def test_happy_path_recomputed_claim_advances(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "ledger.jsonl")
    report = _runner(tmp_path, REPORT_PLAN, ledger=ledger).run(
        {"dataset": "weekly-metrics"}, execution_id="happy"
    )

    assert report.result is RunResult.SUCCEEDED
    assert report.stage_outputs["compile"]["rows"] == 3
    # Acceptance came from recomputation against the dataset, not schema alone.
    assert report.verdicts[-1].accepted is True
    assert report.verdicts[-1].method == "recomputation"

    replayed = ExecutionMachine.replay(REPORT_PLAN, ledger, "happy")
    assert replayed.status is ExecutionStatus.SUCCEEDED
    assert replayed.units[UnitRef("compile")].status is StageStatus.COMPLETED


def test_recomputation_rejects_fabricated_overclaim(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "ledger.jsonl")
    # The fabricator claims rows=100 while weekly-metrics holds 3. The claim is
    # schema-valid (rows minimum 1) yet contradicts the recomputed ground truth.
    report = _runner(tmp_path, FABRICATED_PLAN, ledger=ledger).run(
        {"dataset": "weekly-metrics"}, execution_id="fabricated"
    )

    assert report.result is RunResult.REJECTED
    assert report.rejected_stage == "compile"
    assert report.stage_outputs["compile"]["rows"] == 100  # producer overclaimed
    verdict = report.verdicts[-1]
    assert verdict.accepted is False
    assert verdict.method == "recomputation"
    assert "recomputed ground truth" in verdict.reason

    events = [event["type"] for event in ledger.read("fabricated")]
    assert "unit.claimed" in events
    assert "unit.completed" not in events
    recorded = next(e for e in ledger.read("fabricated") if e["type"] == "evidence.recorded")
    assert recorded["payload"]["accepted"] is False
    replayed = ExecutionMachine.replay(FABRICATED_PLAN, ledger, "fabricated")
    assert replayed.units[UnitRef("compile")].status is StageStatus.FAILED


def test_recomputation_is_independent_of_producer_artifact(tmp_path: Path) -> None:
    # Directly exercise the verifier: hand it a workspace whose artifact claims an
    # inflated row count. Recomputation from the dataset must still reject it.
    workspace = Workspace.create(tmp_path / "workspace")
    verifier = IndependentVerifier(workspace, recomputer=_recomputer())
    stage = REPORT_PLAN.stage_map["compile"]
    artifact_path = workspace.evidence_path("compile", "report-artifact")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        '{"dataset":"weekly-metrics","rows":999,"generatedBy":"compile-report"}',
        encoding="utf-8",
    )
    verdict = verifier.verify(stage, "report-artifact", {"dataset": "weekly-metrics"})
    assert verdict.accepted is False
    assert verdict.method == "recomputation"


def test_rejected_evidence_does_not_advance_unit(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "ledger.jsonl")
    report = _runner(tmp_path, REPORT_PLAN, ledger=ledger).run(
        {"dataset": "empty-dataset"}, execution_id="rejected"
    )

    assert report.result is RunResult.REJECTED
    assert report.rejected_stage == "compile"
    assert report.verdicts[-1].accepted is False

    replayed = ExecutionMachine.replay(REPORT_PLAN, ledger, "rejected")
    assert replayed.status is ExecutionStatus.FAILED
    assert replayed.units[UnitRef("compile")].status is StageStatus.FAILED

    events = [event["type"] for event in ledger.read("rejected")]
    assert "unit.claimed" in events
    assert "unit.completed" not in events


def test_authority_denies_ungranted_external_pre_dispatch(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "ledger.jsonl")
    report = _runner(tmp_path, PUBLISH_PLAN, ledger=ledger).run(
        {"artifact": "evidence/x.json"}, execution_id="denied"
    )

    assert report.result is RunResult.DENIED
    assert report.denied_stage == "publish"
    assert report.execution_status == "failed"
    assert report.authority_decisions["publish"].allowed is False

    events = [event["type"] for event in ledger.read("denied")]
    assert "authorization.requested" in events
    decided = next(e for e in ledger.read("denied") if e["type"] == "authorization.decided")
    assert decided["payload"]["approved"] is False
    assert "execution.failed" in events
    assert "unit.started" not in events
    replayed = ExecutionMachine.replay(PUBLISH_PLAN, ledger, "denied")
    assert replayed.units[UnitRef("publish")].status is StageStatus.FAILED


def test_explicit_external_grant_lets_the_same_stage_proceed(tmp_path: Path) -> None:
    report = _runner(tmp_path, PUBLISH_PLAN, grant=AuthorityGrant(allow_external=True)).run(
        {"artifact": "evidence/x.json"}, execution_id="granted"
    )
    assert report.result is RunResult.SUCCEEDED
    assert report.authority_decisions["publish"].allowed is True
    assert report.stage_outputs["publish"]["receiptId"].startswith("pub-")


def test_independent_verifier_rejects_a_missing_artifact(tmp_path: Path) -> None:
    workspace = Workspace.create(tmp_path / "workspace")
    verifier = IndependentVerifier(workspace)
    compile_stage = REPORT_PLAN.stage_map["compile"]
    verdict = verifier.verify(compile_stage, "report-artifact")
    assert verdict.accepted is False
    assert "not produced" in verdict.reason


def test_workspace_confinement_rejects_traversal(tmp_path: Path) -> None:
    workspace = Workspace.create(tmp_path / "workspace")
    assert workspace.contains(workspace.root / "evidence" / "a.json")
    assert not workspace.contains(workspace.root / ".." / "escape.json")
    assert not workspace.contains(tmp_path / "outside.json")


def test_preflight_rejects_ungated_external_stage(tmp_path: Path) -> None:
    raw = load_domain_pack(PACK_DIR / "domainpack.yaml").to_dict()
    for policy in raw["policies"]:
        if policy["id"] == "external-authorized":
            policy["humanApproval"] = "never"
    broken = parse_domain_pack(raw)
    plan = compile_plan(broken, entrypoint_id="publish")
    with pytest.raises(ConfigurationError, match="deny-by-default"):
        _runner(tmp_path, plan)


def test_preflight_rejects_fanout_each_stage(tmp_path: Path) -> None:
    hello = load_domain_pack(ROOT / "examples" / "hello-domain" / "domainpack.yaml")
    plan = compile_plan(hello, entrypoint_id="hello")
    with pytest.raises(ConfigurationError, match="singleton stages only"):
        _runner(tmp_path, plan)


# --- LLM producer episode harness ---------------------------------------------


def test_episode_replay_correct_smoke_advances(tmp_path: Path) -> None:
    episode = load_episode(EPISODES_DIR / "episode-synthetic-smoke.json")
    assert episode.provenance == "synthetic-smoke"
    assert episode.citable is False  # synthetic-smoke must not be cited
    ledger = JsonlLedger(tmp_path / "ledger.jsonl")
    report = replay_episode(
        episode,
        plan=REPORT_PLAN,
        pack_dir=PACK_DIR,
        workspace=Workspace.create(tmp_path / "workspace"),
        ledger=ledger,
        execution_id="ep-ok",
        recomputer=_recomputer(),
    )
    assert report.result is RunResult.SUCCEEDED
    assert report.verdicts[-1].method == "recomputation"
    assert ExecutionMachine.replay(REPORT_PLAN, ledger, "ep-ok").status is ExecutionStatus.SUCCEEDED


def test_episode_replay_adversarial_smoke_is_rejected(tmp_path: Path) -> None:
    episode = load_episode(EPISODES_DIR / "episode-synthetic-smoke-adversarial.json")
    assert episode.adversarial is True
    report = replay_episode(
        episode,
        plan=REPORT_PLAN,
        pack_dir=PACK_DIR,
        workspace=Workspace.create(tmp_path / "workspace"),
        ledger=JsonlLedger(tmp_path / "ledger.jsonl"),
        execution_id="ep-adv",
        recomputer=_recomputer(),
    )
    # The recorded model output overclaims; recomputation rejects it through the
    # same governed path a subprocess producer would take.
    assert report.result is RunResult.REJECTED
    assert report.verdicts[-1].method == "recomputation"
    assert "recomputed ground truth" in report.verdicts[-1].reason


def test_episode_placeholder_fixture_refuses_replay(tmp_path: Path) -> None:
    placeholder = tmp_path / "episode-placeholder.json"
    placeholder.write_text(
        json.dumps(
            {
                "schema": "contractplane.dev/experimental/producer-episode/v0",
                "provenance": "placeholder",
                "status": "unrecorded",
                "flow": "report",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EpisodeError, match="unrecorded placeholder"):
        load_episode(placeholder)


def test_recorded_episode_slots_are_real_recorded() -> None:
    for name, adversarial in (
        ("episode-correct.json", False),
        ("episode-adversarial.json", True),
    ):
        episode = load_episode(EPISODES_DIR / name)
        assert episode.provenance == "real-recorded"
        assert episode.adversarial is adversarial


def test_episode_format_validation_rejects_bad_transcripts() -> None:
    with pytest.raises(EpisodeError, match="schema"):
        parse_episode({"provenance": "real-recorded", "flow": "report"})
    with pytest.raises(EpisodeError, match="provenance"):
        parse_episode(
            {
                "schema": "contractplane.dev/experimental/producer-episode/v0",
                "provenance": "hand-authored",
                "flow": "report",
                "input": {},
                "claim": {"outputs": {}},
            }
        )


# --- additional recomputable task families (subprocess producers) -------------


def _family_runner(tmp_path: Path, plan, ledger: JsonlLedger | None = None) -> GovernedRunner:
    return GovernedRunner(
        plan,
        pack_dir=PACK_DIR,
        workspace=Workspace.create(tmp_path / "workspace"),
        ledger=ledger or JsonlLedger(tmp_path / "ledger.jsonl"),
        recomputer=_chain(),
    )


def test_aggregate_family_recomputes_column_total(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "ledger.jsonl")
    report = _family_runner(tmp_path, AGGREGATE_PLAN, ledger).run(
        {"dataset": "monthly-metrics"}, execution_id="agg"
    )
    assert report.result is RunResult.SUCCEEDED
    assert report.stage_outputs["aggregate"]["total"] == 780
    assert report.verdicts[-1].method == "recomputation"
    assert ExecutionMachine.replay(AGGREGATE_PLAN, ledger, "agg").units[UnitRef("aggregate")].status is StageStatus.COMPLETED


def test_filter_count_family_recomputes_threshold_count(tmp_path: Path) -> None:
    report = _family_runner(tmp_path, FILTER_PLAN).run(
        {"dataset": "sprint-metrics"}, execution_id="fil"
    )
    assert report.result is RunResult.SUCCEEDED
    # sprint-metrics values [5,15,8,25,3,12,30] above threshold 10 -> 4.
    assert report.stage_outputs["filter"]["matches"] == 4
    assert report.verdicts[-1].method == "recomputation"


def test_new_family_recomputers_reject_direct_fabrication(tmp_path: Path) -> None:
    # A fabricated aggregate artifact that passes schema is still rejected because
    # the recomputed column total disagrees.
    workspace = Workspace.create(tmp_path / "workspace")
    verifier = IndependentVerifier(workspace, recomputer=_chain())
    stage = AGGREGATE_PLAN.stage_map["aggregate"]
    path = workspace.evidence_path("aggregate", "aggregate-artifact")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"dataset":"monthly-metrics","total":424242,"generatedBy":"aggregate-metric"}',
        encoding="utf-8",
    )
    verdict = verifier.verify(stage, "aggregate-artifact", {"dataset": "monthly-metrics"})
    assert verdict.accepted is False
    assert verdict.method == "recomputation"
