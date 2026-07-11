"""Tests for the experimental multi-step agentic claim-chain study.

EXPERIMENTAL — covers contractplane.experimental.chain_study: the 3-step chain
flow, per-step recompute-verification, and the chain-level measurement of error
propagation vs blast-radius containment. Uses only synthetic-smoke chains (never
citable) plus the real placeholder slots (which must skip).
"""

from __future__ import annotations

from pathlib import Path

import json

import pytest

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    ChainDerivedRecomputer,
    ChainEpisodeError,
    load_chain_episode,
    parse_chain_episode,
    run_chain_study,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
CHAIN_DIR = PACK_DIR / "episodes" / "study-chain"
CHAIN_SMOKE_DIR = PACK_DIR / "episodes" / "study-chain-smoke"

# Pinned truths for the chain datasets (X=hard-count-f, Y=hard-count-g2).
TRUE_COUNT = 273
TRUE_SUM = 38808
TRUE_DERIVED = TRUE_COUNT + TRUE_SUM  # 39081


def _study(study_dir: Path) -> dict:
    return run_chain_study(study_dir, pack_dir=PACK_DIR, datasets_dir=DATASETS_DIR)


def _by_file(report: dict) -> dict[str, dict]:
    return {e["file"]: e for e in report["episodes"]}


def test_chain_flow_compiles_into_count_sum_then_derive() -> None:
    plan = compile_plan(PACK, entrypoint_id="chain")
    waves = [[s.id for s in wave.stages] for wave in plan.waves]
    assert waves == [["count", "sum"], ["derive"]]


def test_derived_recomputer_pins_end_to_end_ground_truth() -> None:
    recomputer = ChainDerivedRecomputer(DATASETS_DIR)
    expected = recomputer.recompute(
        None, "chain-derived-artifact", {"datasetX": "hard-count-f", "datasetY": "hard-count-g2"}
    )
    assert expected == {"derived": TRUE_DERIVED}


def test_correct_chain_advances_all_three_steps() -> None:
    report = _study(CHAIN_SMOKE_DIR)
    correct = _by_file(report)["episode-smoke-correct.json"]
    assert [s["verdict"] for s in correct["steps"]] == ["accepted", "accepted", "accepted"]
    assert [s["error"] for s in correct["steps"]] == [False, False, False]
    assert correct["governedResult"] == "succeeded"
    assert correct["derivedClaim"] == correct["derivedTruth"] == TRUE_DERIVED
    assert correct["blastRadiusContained"] is False
    assert correct["errorPropagatedIntoFinalClaim"] is False


def test_early_error_propagates_in_claim_but_is_contained_by_governance() -> None:
    report = _study(CHAIN_SMOKE_DIR)
    err = _by_file(report)["episode-smoke-step1error.json"]
    steps = {s["step"]: s for s in err["steps"]}

    # Step 1 is wrong and rejected; later steps are never reached (contained).
    assert steps["count"]["claimed"] == 280 and steps["count"]["truth"] == TRUE_COUNT
    assert steps["count"]["error"] is True and steps["count"]["verdict"] == "rejected"
    assert steps["sum"]["verdict"] == "not-reached"
    assert steps["derive"]["verdict"] == "not-reached"

    assert err["governedResult"] == "rejected"
    assert err["haltedAtStep"] == "count"
    assert err["firstErrorStep"] == "count"

    # The model's own derived claim inherited the step-1 error (what an ungoverned
    # chain would accept): 280 + 38808 = 39088, not the true 39081.
    assert err["derivedClaim"] == 39088
    assert err["derivedTruth"] == TRUE_DERIVED
    assert err["derivedFromOwnArithmetic"] == 39088
    assert err["derivedMatchesOwnArithmetic"] is True
    assert err["errorPropagatedIntoFinalClaim"] is True

    # Governance contained the blast radius: the derived output was never accepted.
    assert err["blastRadiusContained"] is True


def test_chain_study_summary_counts_propagation_and_containment() -> None:
    summary = _study(CHAIN_SMOKE_DIR)["summary"]
    assert summary["recorded"] == 2
    assert summary["chainsFullyAccepted"] == 1
    assert summary["chainsRejected"] == 1
    assert summary["earlyErrorChains"] == 1
    assert summary["earlyErrorsPropagatedInClaim"] == 1
    assert summary["earlyErrorsContainedByGovernance"] == 1


def test_chain_grid_is_fully_recorded_with_pinned_outcomes() -> None:
    # The three chain slots have been recorded by live agents; pin the
    # governed outcomes as a regression guard.
    report = _study(CHAIN_DIR)
    assert report["summary"]["total"] == 3
    assert report["summary"]["recorded"] == 3
    assert report["summary"]["skipped"] == 0
    assert report["summary"]["chainsFullyAccepted"] == 2
    assert report["summary"]["earlyErrorChains"] == 1
    assert report["summary"]["earlyErrorsContainedByGovernance"] == 1
    assert report["summary"]["earlyErrorsPropagatedInClaim"] == 1


def test_chain_placeholder_fixture_refuses_replay(tmp_path: Path) -> None:
    placeholder = tmp_path / "episode-x-chain1.json"
    placeholder.write_text(
        json.dumps(
            {
                "schema": "contractplane.dev/experimental/chain-episode/v0",
                "provenance": "placeholder",
                "status": "unrecorded",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ChainEpisodeError, match="unrecorded placeholder"):
        load_chain_episode(placeholder)


def test_parse_chain_episode_validates_structure() -> None:
    with pytest.raises(ChainEpisodeError, match="chain-episode"):
        parse_chain_episode({"schema": "x", "provenance": "real-recorded", "flow": "chain"})
    with pytest.raises(ChainEpisodeError, match="exactly 3 steps"):
        parse_chain_episode(
            {
                "schema": "contractplane.dev/experimental/producer-episode/v0",
                "kind": "chain-episode",
                "provenance": "synthetic-smoke",
                "flow": "chain",
                "input": {"datasetX": "hard-count-f", "datasetY": "hard-count-g2"},
                "steps": [],
            }
        )
