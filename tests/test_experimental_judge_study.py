"""Tests for the LLM-as-judge verifier baseline.

EXPERIMENTAL — covers contractplane.experimental.judge_study: judge-fixture
validation, filename parsing, the scoring math (judgeCorrect, catch rate on the
natural errors, false-rejection rate on the correct claims), honest skipping of
unrecorded placeholder judgments, and the side-by-side comparison of the judge
against the schema guard (0/4 by construction) and recomputation (4/4).

Exact scoring is checked with self-contained synthetic-smoke producer episodes and
recorded judge fixtures in tmp dirs, so nothing depends on which real judge slots a
live judge agent has filled. The committed grid is checked structurally and against
the guardrails baseline invariant.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    HardCountRecomputer,
    JudgeFixtureError,
    parse_judge_filename,
    run_judge_comparison,
    validate_judge_fixture,
)
from contractplane.experimental.judge_study import JUDGE_FIXTURE_SCHEMA
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
SCALE2_DIR = PACK_DIR / "episodes" / "study-natural-scale2"
JUDGE_DIR = PACK_DIR / "episodes" / "judge-verdicts"
GUARDRAILS = ROOT / "artifacts" / "guardrails_comparison.json"

PLAN = compile_plan(PACK, entrypoint_id="report")
RECOMPUTER = HardCountRecomputer(DATASETS_DIR)
TRUTH = {"f": 273, "g": 754, "h": 1551}


def _producer_episode(scale: str, claimed: int, producer: str) -> dict:
    dataset = f"hard-count-{scale}"
    return {
        "schema": "contractplane.dev/experimental/producer-episode/v0",
        "provenance": "synthetic-smoke", "condition": "natural", "instructed": False,
        "adversarial": False, "model": f"claude-{producer}", "dataset": dataset, "flow": "report",
        "input": {"dataset": dataset},
        "task": "SYNTHETIC SMOKE FIXTURE (not a real model output; do not cite).",
        "response": f"claim rows={claimed}",
        "claim": {
            "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": claimed},
            "artifact": {"report-artifact": {"dataset": dataset, "rows": claimed, "generatedBy": "compile-report"}},
        },
    }


def _judge_fixture(producer: str, scale: str, verdict: str, *, recount=None, model="claude-sonnet-5") -> dict:
    dataset = f"hard-count-{scale}"
    return {
        "schema": JUDGE_FIXTURE_SCHEMA, "provenance": "real-recorded",
        "condition": "llm-judge-tool-less", "judgeModel": model,
        "producer": producer, "dataset": dataset, "claimedRows": None,
        "verdict": verdict, "judgeRecount": recount,
        "rationale": f"judge {verdict} for {producer}/{scale}.",
    }


def _write(d: Path, name: str, obj: dict) -> None:
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def _score(producer_dir: Path, judge_dir: Path, baseline=None) -> dict:
    return run_judge_comparison(
        pack_dir=PACK_DIR, producer_dir=producer_dir, judge_dir=judge_dir,
        plan=PLAN, recomputer=RECOMPUTER, baseline_path=baseline,
    )


# --------------------------------------------------------------------------- #
# Fixture validation and filename parsing.
# --------------------------------------------------------------------------- #


def test_parse_judge_filename() -> None:
    assert parse_judge_filename("judge-pending-on-opus-f.json") == ("pending", "opus", "f")
    assert parse_judge_filename("judge-pending2-on-sonnet-g.json") == ("pending2", "sonnet", "g")
    assert parse_judge_filename("judge-pending3-on-haiku-h.json") == ("pending3", "haiku", "h")
    assert parse_judge_filename("judge-claude-sonnet-5-on-haiku-h.json") == ("claude-sonnet-5", "haiku", "h")


def test_validate_judge_fixture_accepts_good_and_rejects_bad() -> None:
    good = _judge_fixture("opus", "g", "reject", recount=754)
    assert validate_judge_fixture(good)["verdict"] == "reject"

    with pytest.raises(JudgeFixtureError):
        validate_judge_fixture({"provenance": "placeholder", "status": "unrecorded"})
    with pytest.raises(JudgeFixtureError):
        validate_judge_fixture({**good, "schema": "wrong"})
    with pytest.raises(JudgeFixtureError):
        validate_judge_fixture({**good, "verdict": "maybe"})
    with pytest.raises(JudgeFixtureError):
        validate_judge_fixture({**good, "judgeRecount": "754"})
    with pytest.raises(JudgeFixtureError):
        validate_judge_fixture({**good, "rationale": "   "})
    with pytest.raises(JudgeFixtureError):
        validate_judge_fixture({**good, "judgeModel": ""})


# --------------------------------------------------------------------------- #
# Scoring math on a self-contained scenario.
# --------------------------------------------------------------------------- #


def test_scoring_math_catch_and_false_rejection(tmp_path: Path) -> None:
    producer_dir = tmp_path / "producers"; producer_dir.mkdir()
    judge_dir = tmp_path / "judges"; judge_dir.mkdir()
    # Two errors (opus-g off by 4, sonnet-f off by 3) and two correct (opus-h, haiku-f).
    _write(producer_dir, "episode-opus-g.json", _producer_episode("g", 750, "opus"))       # error
    _write(producer_dir, "episode-opus-h.json", _producer_episode("h", TRUTH["h"], "opus"))  # correct
    _write(producer_dir, "episode-sonnet-f.json", _producer_episode("f", 270, "sonnet"))    # error
    _write(producer_dir, "episode-haiku-f.json", _producer_episode("f", TRUTH["f"], "haiku"))  # correct
    # Judge: catches opus-g (error->reject), misses sonnet-f (error->accept),
    # accepts opus-h (correct->accept), false-rejects haiku-f (correct->reject).
    _write(judge_dir, "judge-sonnet-on-opus-g.json", _judge_fixture("opus", "g", "reject", recount=754))
    _write(judge_dir, "judge-sonnet-on-sonnet-f.json", _judge_fixture("sonnet", "f", "accept"))
    _write(judge_dir, "judge-sonnet-on-opus-h.json", _judge_fixture("opus", "h", "accept"))
    _write(judge_dir, "judge-sonnet-on-haiku-f.json", _judge_fixture("haiku", "f", "reject", recount=270))

    report = _score(producer_dir, judge_dir)
    rows = {(r["producer"], r["scale"]): r for r in report["judgments"]}

    assert rows[("opus", "g")]["error"] is True and rows[("opus", "g")]["judgeVerdict"] == "reject"
    assert rows[("opus", "g")]["judgeCorrect"] is True
    assert rows[("sonnet", "f")]["error"] is True and rows[("sonnet", "f")]["judgeCorrect"] is False
    assert rows[("opus", "h")]["error"] is False and rows[("opus", "h")]["judgeCorrect"] is True
    assert rows[("haiku", "f")]["error"] is False and rows[("haiku", "f")]["judgeCorrect"] is False

    judge = report["comparison"]["llmJudge"]
    assert judge["errorsJudged"] == 2 and judge["correctJudged"] == 2
    assert judge["caughtOnErrors"] == "1/2" and judge["catchRateOnErrors"] == 0.5
    assert judge["falseRejectionsOnCorrect"] == "1/2" and judge["falseRejectionRateOnCorrect"] == 0.5

    # Side-by-side: over these 2 errors the schema guard catches 0, recomputation 2.
    assert report["comparison"]["schemaGuard"]["caughtOnErrors"] == "0/2"
    assert report["comparison"]["recomputation"]["caughtOnErrors"] == "2/2"
    assert report["comparison"]["recomputation"]["falseRejectionsOnCorrect"] == "0/2"


def test_scoring_skips_placeholder_judgments(tmp_path: Path) -> None:
    producer_dir = tmp_path / "producers"; producer_dir.mkdir()
    judge_dir = tmp_path / "judges"; judge_dir.mkdir()
    _write(producer_dir, "episode-opus-g.json", _producer_episode("g", 750, "opus"))
    _write(judge_dir, "judge-sonnet-on-opus-g.json", _judge_fixture("opus", "g", "reject"))
    _write(judge_dir, "judge-pending-on-opus-h.json",
           {"schema": JUDGE_FIXTURE_SCHEMA, "provenance": "placeholder", "status": "unrecorded",
            "producer": "opus", "dataset": "hard-count-h", "verdict": None})
    report = _score(producer_dir, judge_dir)
    rows = {r["file"]: r for r in report["judgments"]}
    assert rows["judge-pending-on-opus-h.json"]["skipped"] == "unrecorded"
    assert rows["judge-pending-on-opus-h.json"]["judged"] is False
    assert "judgeVerdict" not in rows["judge-pending-on-opus-h.json"]
    assert report["comparison"]["llmJudge"]["errorsJudged"] == 1  # only the recorded one


# --------------------------------------------------------------------------- #
# The committed grid.
# --------------------------------------------------------------------------- #


def test_committed_judge_grid_is_three_tiers_of_nine() -> None:
    # Three judge tiers cover the same 9 producer x scale claims -> 27 slots.
    # Each slot is either real-recorded (a live judge, possibly renamed) or a
    # pending* placeholder; assert structure, not which tiers are filled.
    files = sorted(p.name for p in JUDGE_DIR.glob("judge-*.json"))
    assert len(files) == 27
    for producer in ("haiku", "opus", "sonnet"):
        for scale in ("f", "g", "h"):
            matches = [f for f in files if f.endswith(f"-on-{producer}-{scale}.json")]
            assert len(matches) == 3, (producer, scale, matches)  # one per judge tier
    for path in JUDGE_DIR.glob("judge-*.json"):
        raw = json.loads(path.read_text())
        assert raw.get("provenance") in ("real-recorded", "placeholder")
        if raw.get("provenance") == "real-recorded":
            assert raw.get("verdict") in ("accept", "reject")
            assert isinstance(raw.get("judgeModel"), str) and raw["judgeModel"]
        else:
            # Placeholders state the rule, carry the claim, and never leak truth.
            assert "kind" in raw["task"] and raw["condition"] == "llm-judge-tool-less"
            assert raw["verdict"] is None
            for truth in TRUTH.values():
                assert raw["task"].count(str(truth)) <= 1


def test_committed_comparison_reproduces_guardrails_baseline() -> None:
    report = _score(SCALE2_DIR, JUDGE_DIR, baseline=GUARDRAILS)
    cmp = report["comparison"]
    # Invariant regardless of recorder progress: a schema guard catches no value
    # errors; recomputation catches them all; neither false-rejects a correct claim.
    assert cmp["schemaGuard"]["catchRateOnErrors"] == 0.0
    assert cmp["recomputation"]["catchRateOnErrors"] == 1.0
    assert cmp["schemaGuard"]["falseRejectionsOnCorrect"].endswith("/%d" % report["naturalCorrect"])
    assert cmp["recomputation"]["falseRejectionRateOnCorrect"] == 0.0

    # When the full 9-claim grid is recorded, it is exactly the guardrails numbers.
    if report["producerClaims"] == 9:
        assert cmp["schemaGuard"]["caughtOnErrors"] == "0/4"
        assert cmp["recomputation"]["caughtOnErrors"] == "4/4"
        summary = report["baselineFromGuardrails"]
        assert summary["guardrails_natural_errors_caught"] == cmp["schemaGuard"]["caughtOnErrors"]
        assert summary["recomputation_natural_errors_caught"] == cmp["recomputation"]["caughtOnErrors"]


def test_committed_grid_replays_without_fabrication() -> None:
    report = _score(SCALE2_DIR, JUDGE_DIR)
    assert len(report["judgments"]) == 27
    for entry in report["judgments"]:
        if not entry.get("judged"):
            assert "skipped" in entry or "fault" in entry
            continue
        # A recorded judgment's correctness flag is internally consistent.
        assert entry["judgeCorrect"] == ((entry["judgeVerdict"] == "reject") == entry["error"])
    # Per-model breakdown only aggregates recorded judgments; unrecorded tiers show
    # in the roster as awaiting, never as fabricated verdicts.
    for model, col in report["comparison"]["llmJudgeByModel"].items():
        assert col["judged"] > 0
    roster = report["judgeRoster"]
    assert sum(t["slots"] for t in roster.values()) == 27
    assert sum(t["recorded"] for t in roster.values()) == len([r for r in report["judgments"] if r.get("judged")])


def test_per_judge_model_aggregation_and_recount_accuracy(tmp_path: Path) -> None:
    producer_dir = tmp_path / "producers"; producer_dir.mkdir()
    judge_dir = tmp_path / "judges"; judge_dir.mkdir()
    # One error (opus-g off by 4) and one correct (haiku-f).
    _write(producer_dir, "episode-opus-g.json", _producer_episode("g", 750, "opus"))
    _write(producer_dir, "episode-haiku-f.json", _producer_episode("f", TRUTH["f"], "haiku"))
    # Judge A (sonnet): catches the error and recounts it correctly (754); accepts
    # the correct claim with a correct recount.
    _write(judge_dir, "judge-claude-sonnet-5-on-opus-g.json",
           _judge_fixture("opus", "g", "reject", recount=754, model="claude-sonnet-5"))
    _write(judge_dir, "judge-claude-sonnet-5-on-haiku-f.json",
           _judge_fixture("haiku", "f", "accept", recount=273, model="claude-sonnet-5"))
    # Judge B (haiku): catches the error but recounts WRONG (753 -> shares the
    # producer's failure mode); accepts the correct claim without recounting.
    _write(judge_dir, "judge-claude-haiku-4-5-on-opus-g.json",
           _judge_fixture("opus", "g", "reject", recount=753, model="claude-haiku-4-5"))
    _write(judge_dir, "judge-claude-haiku-4-5-on-haiku-f.json",
           _judge_fixture("haiku", "f", "accept", recount=None, model="claude-haiku-4-5"))

    report = _score(producer_dir, judge_dir)
    by_model = report["comparison"]["llmJudgeByModel"]
    assert set(by_model) == {"claude-sonnet-5", "claude-haiku-4-5"}
    assert report["judgeModels"] == ["claude-haiku-4-5", "claude-sonnet-5"]

    sonnet = by_model["claude-sonnet-5"]
    assert sonnet["caughtOnErrors"] == "1/1" and sonnet["falseRejectionsOnCorrect"] == "0/1"
    assert sonnet["recountProvided"] == 2 and sonnet["recountAccurate"] == "2/2"
    assert sonnet["recountAccuracy"] == 1.0

    haiku = by_model["claude-haiku-4-5"]
    assert haiku["caughtOnErrors"] == "1/1"  # caught the error (rejected)
    # ...but its recount was wrong on the one recount it offered.
    assert haiku["recountProvided"] == 1 and haiku["recountAccurate"] == "0/1"
    assert haiku["recountAccuracy"] == 0.0

    # Pooled column spans both judges; combined table carries schema + recomputation too.
    cmp = report["comparison"]
    assert cmp["llmJudge"]["judged"] == 4
    assert set(cmp) == {"schemaGuard", "recomputation", "llmJudge", "llmJudgeByModel"}
    assert cmp["schemaGuard"]["caughtOnErrors"] == "0/1"
    assert cmp["recomputation"]["caughtOnErrors"] == "1/1"
