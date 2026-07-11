"""Tests for the consistency-vote verifier baselines and Fisher exact tests.

EXPERIMENTAL — covers contractplane.experimental.consistency_study (cross-judge
majority-recount + same-model attempt-consistency, derived from already-recorded
data) and the fisher_exact_two_sided helper wired into the power study.

The derived verdicts and the three pairwise p-values are pinned against the
committed recordings (that is the point — the paper cites these numbers); the vote
and Fisher algorithms also have data-independent unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    HardCountRecomputer,
    fisher_exact_two_sided,
    run_consistency_study,
)
from contractplane.experimental.consistency_study import _majority
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
SCALE2_DIR = PACK_DIR / "episodes" / "study-natural-scale2"
JUDGE_DIR = PACK_DIR / "episodes" / "judge-verdicts"

PLAN = compile_plan(PACK, entrypoint_id="report")
RECOMPUTER = HardCountRecomputer(DATASETS_DIR)


def _study() -> dict:
    return run_consistency_study(
        pack_dir=PACK_DIR, producer_dir=SCALE2_DIR, judge_dir=JUDGE_DIR,
        plan=PLAN, recomputer=RECOMPUTER,
    )


# --------------------------------------------------------------------------- #
# Majority helper (data-independent).
# --------------------------------------------------------------------------- #


def test_majority_helper() -> None:
    assert _majority([754, 754, 754]) == (754, False)
    assert _majority([754, 754, 753]) == (754, False)
    assert _majority([1552, 1551, 1548]) == (None, True)   # all disagree -> abstain
    assert _majority([754, None, 754]) == (754, False)
    assert _majority([None, None, None]) == (None, True)
    assert _majority([754, 753]) == (None, True)           # tie -> no majority


# --------------------------------------------------------------------------- #
# Cross-judge majority-recount verifier (committed data).
# --------------------------------------------------------------------------- #


def test_cross_judge_majority_recount_catches_one_and_abstains_on_three() -> None:
    report = _study()
    cj = report["crossJudgeMajorityRecount"]
    agg = cj["aggregate"]
    # It catches only opus-g (all three judges agree on 754 != claimed 753) and
    # ABSTAINS on all three h-band errors, where the judges' recounts all disagree.
    assert agg["errors"] == 4 and agg["correct"] == 5
    assert agg["caughtOnErrors"] == "1/4"
    assert agg["falseRejectionsOnCorrect"] == "0/5"
    assert agg["abstainedOnErrors"] == 3

    rows = {(r["producer"], r["dataset"]): r for r in cj["perClaim"]}
    caught = rows[("opus", "hard-count-g")]
    assert caught["error"] and caught["verdict"] == "reject" and caught["caught"]
    missed = rows[("haiku", "hard-count-h")]
    assert missed["error"] and missed["abstained"] and missed["verdict"] == "accept"
    assert missed["caught"] is False


def test_comparison_table_places_consistency_beside_existing_tiers() -> None:
    report = _study()
    v = report["comparison"]["verifiers"]
    assert v["schemaGuard"]["caughtOnErrors"] == "0/4"
    assert v["recomputation"]["caughtOnErrors"] == "4/4"
    assert v["crossJudgeMajorityRecount"]["caughtOnErrors"] == "1/4"
    # Single judges (by verdict) actually beat the naive majority-recount vote.
    assert v["singleJudge/claude-opus-4-8"]["caughtOnErrors"] == "3/4"
    assert v["singleJudge/claude-sonnet-5"]["caughtOnErrors"] == "4/4"
    assert v["singleJudge/claude-haiku-4-5"]["caughtOnErrors"] == "4/4"
    # No verifier here false-rejects a correct claim.
    assert all(col["falseRejectionsOnCorrect"] == "0/5" for col in v.values())


# --------------------------------------------------------------------------- #
# Same-model attempt-consistency verifier (committed data).
# --------------------------------------------------------------------------- #


def test_attempt_consistency_flags_all_first_attempts_including_correct_ones() -> None:
    report = _study()
    ac = report["sameModelAttemptConsistency"]
    agg = ac["aggregate"]
    # Every model drifts across its own tool-less attempts, so self-consistency flags
    # ALL first attempts -- catching all 4 erroneous ones but also false-flagging both
    # correct ones. It is not a usable discriminator.
    assert agg["erroneousFirstAttempts"] == 4
    assert agg["flaggedErroneousFirstAttempts"] == "4/4"
    assert agg["correctFirstAttempts"] == 2
    assert agg["falseFlagsOnCorrectFirst"] == "2/2"
    assert "not fresh" in ac["description"].lower()  # honest labelling

    groups = {(g["model"], g["dataset"]): g for g in ac["perGroup"]}
    false_flag = groups[("sonnet", "hard-count-g")]
    assert false_flag["r1Error"] is False and false_flag["flaggedR1"] is True
    assert false_flag["falseFlagOnCorrect"] is True


def test_consistency_study_writes_expected_scope() -> None:
    report = _study()
    assert report["producerClaims"] == 9
    assert report["naturalErrors"] == 4 and report["naturalCorrect"] == 5
    assert report["comparison"]["scope"].startswith("9 scale2 natural claims")


# --------------------------------------------------------------------------- #
# Fisher exact two-sided (algorithm + pinned p-values).
# --------------------------------------------------------------------------- #


def test_fisher_exact_pinned_pairwise_pvalues() -> None:
    # Per-model natural error counts 2/13, 4/13, 7/13 -> all pairwise non-significant.
    assert fisher_exact_two_sided(2, 11, 4, 9) == 0.64472    # opus vs sonnet
    assert fisher_exact_two_sided(2, 11, 7, 6) == 0.096842   # opus vs haiku
    assert fisher_exact_two_sided(4, 9, 7, 6) == 0.428308    # sonnet vs haiku
    # None of the three reaches significance at 0.05.
    assert all(p > 0.05 for p in (
        fisher_exact_two_sided(2, 11, 4, 9),
        fisher_exact_two_sided(2, 11, 7, 6),
        fisher_exact_two_sided(4, 9, 7, 6),
    ))


def test_fisher_exact_properties() -> None:
    # Symmetric in row order.
    assert fisher_exact_two_sided(2, 11, 7, 6) == fisher_exact_two_sided(7, 6, 2, 11)
    # Identical rows -> p == 1.0.
    assert fisher_exact_two_sided(3, 10, 3, 10) == 1.0
    # A clean separation is highly significant.
    assert fisher_exact_two_sided(10, 0, 0, 10) < 0.001
    # Degenerate margins -> None (no test possible).
    assert fisher_exact_two_sided(0, 0, 5, 5) is None
    assert fisher_exact_two_sided(3, 3, 3, 3) is not None
