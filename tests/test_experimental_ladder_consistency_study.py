"""Tests for the ladder cross-judge consistency-vote verifier (EXPERIMENTAL).

Covers contractplane.experimental.ladder_consistency_study: the cross-judge
majority-recount vote (mirroring consistency_study._cross_judge) extended to the
GPU-ladder judged corpus, so the consistency tier is scored on 16 errors instead
of 4. Two kinds of test:

* Synthetic-fixture math (data-independent): the vote rule, abstention on
  three-way recount disagreement, the single-pass-per-dataset sharing property,
  and the combined-table pooling are checked on hand-built judgment rows.
* Pinned committed numbers: the derived ladder + combined figures are pinned
  against the committed ladder judge grid and the committed scale2 recordings
  (that is the point — the paper cites these numbers).
"""

from __future__ import annotations

from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    HardCountRecomputer,
    run_consistency_study,
    run_ladder_consistency_study,
)
from contractplane.experimental.ladder_consistency_study import (
    _combined_consistency,
    _ladder_cross_judge,
    _within_dataset_recount_sharing,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
GPU_DIR = PACK_DIR / "episodes" / "study-local-gpu"
LADDER_JUDGE_DIR = PACK_DIR / "episodes" / "judge-verdicts-ladder"
SCALE2_DIR = PACK_DIR / "episodes" / "study-natural-scale2"
SCALE2_JUDGE_DIR = PACK_DIR / "episodes" / "judge-verdicts"
ARTIFACT = ROOT / "artifacts" / "local_gpu_family_study.json"

PLAN = compile_plan(PACK, entrypoint_id="report")
RECOMPUTER = HardCountRecomputer(DATASETS_DIR)


def _judged_row(
    stem: str, dataset: str, claimed: int, truth: int, model: str, recount, rank: int
) -> dict:
    return {
        "judged": True,
        "stem": stem,
        "producer": "qwen3:32b",
        "dataset": dataset,
        "rank": rank,
        "claimed": claimed,
        "truth": truth,
        "error": claimed != truth,
        "judgeModel": model,
        "judgeRecount": recount,
    }


# --------------------------------------------------------------------------- #
# Vote rule (data-independent, synthetic judgment rows).
# --------------------------------------------------------------------------- #


def test_ladder_cross_judge_rejects_on_majority_and_abstains_on_disagreement() -> None:
    # Claim A: all three judges recount 273; claimed 274 -> majority 273 -> reject (caught).
    # Claim B: three judges recount 1551/1552/1548 (all disagree); claimed 1550 -> ABSTAIN.
    # Claim C: two judges recount 754, one 768; claimed 767 -> majority 754 -> reject (caught).
    judgments = [
        _judged_row("a", "hard-count-f", 274, 273, "claude-opus-4-8", 273, 1),
        _judged_row("a", "hard-count-f", 274, 273, "claude-sonnet-5", 273, 1),
        _judged_row("a", "hard-count-f", 274, 273, "claude-haiku-4-5", 273, 1),
        _judged_row("b", "hard-count-h", 1550, 1551, "claude-opus-4-8", 1552, 2),
        _judged_row("b", "hard-count-h", 1550, 1551, "claude-sonnet-5", 1548, 2),
        _judged_row("b", "hard-count-h", 1550, 1551, "claude-haiku-4-5", 1551, 2),
        _judged_row("c", "hard-count-g", 767, 754, "claude-opus-4-8", 754, 3),
        _judged_row("c", "hard-count-g", 767, 754, "claude-sonnet-5", 754, 3),
        _judged_row("c", "hard-count-g", 767, 754, "claude-haiku-4-5", 768, 3),
    ]
    block = _ladder_cross_judge(judgments)
    rows = {r["stem"]: r for r in block["perClaim"]}

    assert rows["a"]["majorityRecount"] == 273 and rows["a"]["verdict"] == "reject"
    assert rows["a"]["caught"] is True and rows["a"]["abstained"] is False

    assert rows["b"]["abstained"] is True and rows["b"]["majorityRecount"] is None
    assert rows["b"]["verdict"] == "accept" and rows["b"]["caught"] is False

    assert rows["c"]["majorityRecount"] == 754 and rows["c"]["verdict"] == "reject"
    assert rows["c"]["caught"] is True and rows["c"]["abstained"] is False

    agg = block["aggregate"]
    assert agg["errors"] == 3 and agg["correct"] == 0
    assert agg["caughtOnErrors"] == "2/3"
    assert agg["abstainedOnErrors"] == 1
    assert agg["falseRejectionsOnCorrect"] == "0/0"


def test_within_dataset_sharing_detects_single_pass() -> None:
    # Two f claims share the same three recounts; one g claim has its own triple.
    judgments = [
        _judged_row("a", "hard-count-f", 274, 273, "claude-opus-4-8", 273, 1),
        _judged_row("a", "hard-count-f", 274, 273, "claude-sonnet-5", 273, 1),
        _judged_row("b", "hard-count-f", 275, 273, "claude-opus-4-8", 273, 2),
        _judged_row("b", "hard-count-f", 275, 273, "claude-sonnet-5", 273, 2),
        _judged_row("c", "hard-count-g", 767, 754, "claude-opus-4-8", 754, 3),
        _judged_row("c", "hard-count-g", 767, 754, "claude-sonnet-5", 754, 3),
    ]
    sharing = _within_dataset_recount_sharing(judgments)
    assert sharing["singlePassPerDataset"] is True
    assert sharing["claimsPerDataset"] == {"hard-count-f": 2, "hard-count-g": 1}
    assert sharing["distinctRecountsPerJudgePerDataset"]["hard-count-f"]["claude-opus-4-8"] == [273]


def test_within_dataset_sharing_flags_multiple_passes() -> None:
    # A judge that recounted differently on two same-dataset claims is not single-pass.
    judgments = [
        _judged_row("a", "hard-count-f", 274, 273, "claude-opus-4-8", 273, 1),
        _judged_row("b", "hard-count-f", 275, 273, "claude-opus-4-8", 272, 2),
    ]
    sharing = _within_dataset_recount_sharing(judgments)
    assert sharing["singlePassPerDataset"] is False
    assert sharing["distinctRecountsPerJudgePerDataset"]["hard-count-f"]["claude-opus-4-8"] == [272, 273]


def test_combined_consistency_pools_scale2_and_ladder() -> None:
    ladder_aggregate = {
        "errors": 12,
        "correct": 0,
        "caughtOnErrors": "12/12",
        "falseRejectionsOnCorrect": "0/0",
        "abstainedOnErrors": 0,
    }
    scale2_consistency = {
        "crossJudgeMajorityRecount": {
            "aggregate": {
                "errors": 4,
                "correct": 5,
                "caughtOnErrors": "1/4",
                "falseRejectionsOnCorrect": "0/5",
                "abstainedOnErrors": 3,
            }
        }
    }
    combined = _combined_consistency(ladder_aggregate, scale2_consistency=scale2_consistency)
    assert combined["scale2"]["caughtOnErrors"] == "1/4"
    assert combined["ladder"]["caughtOnErrors"] == "12/12"
    assert combined["combined"]["errors"] == 16
    assert combined["combined"]["caughtOnErrors"] == "13/16"
    assert combined["combined"]["abstainedOnErrors"] == 3
    assert combined["combined"]["falseRejectionsOnCorrect"] == "0/5"


# --------------------------------------------------------------------------- #
# Pinned committed numbers (the paper cites these).
# --------------------------------------------------------------------------- #


def _committed_scale2() -> dict:
    return run_consistency_study(
        pack_dir=PACK_DIR, producer_dir=SCALE2_DIR, judge_dir=SCALE2_JUDGE_DIR,
        plan=PLAN, recomputer=RECOMPUTER,
    )


def _committed_report() -> dict:
    return run_ladder_consistency_study(
        pack_dir=PACK_DIR, gpu_study_dir=GPU_DIR, judge_dir=LADDER_JUDGE_DIR,
        plan=PLAN, recomputer=RECOMPUTER, artifact_path=ARTIFACT,
        scale2_consistency=_committed_scale2(),
    )


def test_committed_ladder_consistency_catches_all_twelve() -> None:
    report = _committed_report()
    block = report["ladderCrossJudgeMajorityRecount"]
    agg = block["aggregate"]
    # Every one of the 12 ladder claims differs from its majority recount, and no
    # claim's three recounts disagree three ways, so the vote catches all 12, abstains 0.
    assert agg["errors"] == 12 and agg["correct"] == 0
    assert agg["caughtOnErrors"] == "12/12"
    assert agg["abstainedOnErrors"] == 0
    assert agg["falseRejectionsOnCorrect"] == "0/0"
    assert len(block["perClaim"]) == 12
    assert all(r["verdict"] == "reject" and r["caught"] for r in block["perClaim"])

    # The lone g claim is caught by a 2/3 majority (haiku recounts 768, opus/sonnet 754).
    g = next(r for r in block["perClaim"] if r["dataset"] == "hard-count-g")
    assert g["claimed"] == 767 and g["majorityRecount"] == 754
    assert sorted(g["judgeRecounts"].values()) == [754, 754, 768]


def test_committed_within_dataset_sharing_is_single_pass() -> None:
    report = _committed_report()
    sharing = report["ladderCrossJudgeMajorityRecount"]["withinDatasetRecountSharing"]
    assert sharing["singlePassPerDataset"] is True
    assert sharing["claimsPerDataset"] == {"hard-count-f": 11, "hard-count-g": 1}
    # All 11 hard-count-f claims are decided by the same recount triple 273/273/273.
    f = sharing["distinctRecountsPerJudgePerDataset"]["hard-count-f"]
    assert f == {
        "claude-haiku-4-5": [273],
        "claude-opus-4-8": [273],
        "claude-sonnet-5": [273],
    }


def test_committed_combined_tier_is_sixteen_errors() -> None:
    report = _committed_report()
    tier = report["combinedConsistencyTier"]
    assert tier["verifier"] == "crossJudgeMajorityRecount"
    assert tier["scale2"]["caughtOnErrors"] == "1/4"
    assert tier["scale2"]["abstainedOnErrors"] == 3
    assert tier["ladder"]["caughtOnErrors"] == "12/12"
    assert tier["ladder"]["abstainedOnErrors"] == 0
    assert tier["combined"]["errors"] == 16
    assert tier["combined"]["caughtOnErrors"] == "13/16"
    assert tier["combined"]["abstainedOnErrors"] == 3
    # The ladder contributes no correct claims; false-rejection evidence stays with scale2.
    assert tier["combined"]["falseRejectionsOnCorrect"] == "0/5"
