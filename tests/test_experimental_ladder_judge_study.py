"""Tests for the GPU-ladder LLM-as-judge baseline (EXPERIMENTAL).

Covers contractplane.experimental.ladder_judge_study: the deterministic selection
of the 12 smallest-|error| ladder claims from the recorded artifact, the committed
36-slot placeholder grid (structure + no truth leak + honest refusal), the scoring
math (judgeCorrect, per-judge-model catch rate, recount accuracy) on self-contained
synthetic tmp fixtures, and the combined-table math merging the scale2 judged errors
(4) with the ladder errors (12) into the 16-error corpus.

Exact scoring is checked with synthetic-smoke producer episodes and recorded judge
fixtures in tmp dirs, so nothing depends on which real judge slots a live judge has
filled. The committed grid is checked structurally.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    HardCountRecomputer,
    LadderSelectionError,
    build_ladder_placeholder,
    ladder_judge_filename,
    parse_ladder_judge_filename,
    run_ladder_judge_study,
    select_ladder_claims,
)
from contractplane.experimental.judge_study import JUDGE_FIXTURE_SCHEMA
from contractplane.experimental.ladder_judge_study import (
    LADDER_JUDGE_TIERS,
    episode_stem,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
GPU_DIR = PACK_DIR / "episodes" / "study-local-gpu"
JUDGE_DIR = PACK_DIR / "episodes" / "judge-verdicts-ladder"
ARTIFACT = ROOT / "artifacts" / "local_gpu_family_study.json"

PLAN = compile_plan(PACK, entrypoint_id="report")
RECOMPUTER = HardCountRecomputer(DATASETS_DIR)
TRUTH = {"f": 273, "g": 754}

# The 12 near-miss producer episodes the selection must resolve to, smallest |err|
# first (ties within the set may reorder, but the set is fixed by the artifact).
EXPECTED_SELECTION = {
    "episode-qwen3-14b-f-13.json",
    "episode-qwen3-14b-f-14.json",
    "episode-qwen3-32b-f-03.json",
    "episode-qwen3-14b-f-02.json",
    "episode-qwen3-32b-f-08.json",
    "episode-qwen3-14b-f-09.json",
    "episode-qwen3-32b-f-05.json",
    "episode-qwen3-32b-f-16.json",
    "episode-qwen3-32b-f-20.json",
    "episode-qwen3-32b-f-17.json",
    "episode-qwen3-32b-f-04.json",
    "episode-qwen3-32b-g-17.json",
}


def _producer_episode(scale: str, claimed: int, model: str) -> dict:
    dataset = f"hard-count-{scale}"
    return {
        "schema": "contractplane.dev/experimental/producer-episode/v0",
        "provenance": "synthetic-smoke", "condition": "natural", "instructed": False,
        "adversarial": False, "model": model, "dataset": dataset, "flow": "report",
        "input": {"dataset": dataset},
        "task": "SYNTHETIC SMOKE FIXTURE (not a real model output; do not cite).",
        "response": f"claim rows={claimed}",
        "claim": {
            "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": claimed},
            "artifact": {"report-artifact": {"dataset": dataset, "rows": claimed, "generatedBy": "compile-report"}},
        },
    }


def _judge_fixture(stem: str, dataset: str, claimed: int, verdict: str, *, recount=None, model="claude-sonnet-5") -> dict:
    return {
        "schema": JUDGE_FIXTURE_SCHEMA, "provenance": "real-recorded",
        "condition": "llm-judge-tool-less", "judgeModel": model,
        "producerModel": "qwen3:32b", "dataset": dataset, "sourceEpisode": f"episode-{stem}.json",
        "claimedRows": claimed, "verdict": verdict, "judgeRecount": recount,
        "rationale": f"judge {verdict} for {stem}.",
    }


def _write(d: Path, name: str, obj: dict) -> None:
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def _fake_artifact(rows: list[dict]) -> dict:
    return {"schema": "x", "episodes": rows}


def _write_artifact(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(_fake_artifact(rows)), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Filename helpers.
# --------------------------------------------------------------------------- #


def test_parse_and_build_ladder_judge_filename() -> None:
    assert episode_stem("episode-qwen3-32b-g-17.json") == "qwen3-32b-g-17"
    assert parse_ladder_judge_filename("judge-pending-on-qwen3-32b-g-17.json") == (
        "pending", "qwen3-32b-g-17",
    )
    assert parse_ladder_judge_filename("judge-claude-opus-4-8-on-qwen3-14b-f-13.json") == (
        "claude-opus-4-8", "qwen3-14b-f-13",
    )
    assert ladder_judge_filename("pending2", "episode-qwen3-14b-f-02.json") == (
        "judge-pending2-on-qwen3-14b-f-02.json"
    )


# --------------------------------------------------------------------------- #
# Selection logic.
# --------------------------------------------------------------------------- #


def test_selection_picks_twelve_smallest_abs_error_from_committed_artifact() -> None:
    claims = select_ladder_claims(ARTIFACT, k=12)
    assert len(claims) == 12
    assert {c["file"] for c in claims} == EXPECTED_SELECTION
    # Ordered smallest-|error| first, and every selected claim is below the boundary.
    errs = [c["absoluteError"] for c in claims]
    assert errs == sorted(errs)
    assert max(errs) == 13  # the 12th-smallest natural error in the ladder
    # All are qwen3:14b/32b on hard-count-f/g near-misses.
    assert {c["model"] for c in claims} <= {"qwen3:14b", "qwen3:32b"}
    assert {c["dataset"] for c in claims} <= {"hard-count-f", "hard-count-g"}


def test_selection_is_deterministic_and_respects_f_over_g_tiebreak(tmp_path: Path) -> None:
    rows = [
        {"file": "episode-m-g-01.json", "model": "qwen3:32b", "dataset": "hard-count-g",
         "attempt": "01", "claimed": 700, "absoluteError": 5, "error": True},
        {"file": "episode-m-f-01.json", "model": "qwen3:14b", "dataset": "hard-count-f",
         "attempt": "01", "claimed": 270, "absoluteError": 5, "error": True},
        {"file": "episode-m-f-02.json", "model": "qwen3:32b", "dataset": "hard-count-f",
         "attempt": "02", "claimed": 260, "absoluteError": 9, "error": True},
        # Non-errors and parse-failures are never candidates.
        {"file": "episode-m-f-03.json", "model": "qwen3:32b", "dataset": "hard-count-f",
         "attempt": "03", "claimed": 273, "absoluteError": 0, "error": False},
        {"file": "episode-m-f-04.json", "model": "qwen3:8b", "dataset": "hard-count-f",
         "attempt": "04", "claimed": None, "parseFailure": True},
    ]
    picked = select_ladder_claims(_write_artifact(tmp_path, rows), k=2)
    # Tie at |err|=5 breaks f-before-g; the non-error and parse-failure are excluded.
    assert [c["file"] for c in picked] == ["episode-m-f-01.json", "episode-m-g-01.json"]


def test_selection_raises_when_too_few_errors(tmp_path: Path) -> None:
    rows = [{"file": "episode-m-f-01.json", "model": "m", "dataset": "hard-count-f",
             "attempt": "01", "claimed": 270, "absoluteError": 3, "error": True}]
    with pytest.raises(LadderSelectionError):
        select_ladder_claims(_write_artifact(tmp_path, rows), k=12)


# --------------------------------------------------------------------------- #
# The committed 36-slot grid.
# --------------------------------------------------------------------------- #


def test_committed_grid_is_three_tiers_of_twelve_no_truth_leak() -> None:
    files = sorted(p.name for p in JUDGE_DIR.glob("judge-*.json"))
    assert len(files) == 36
    stems = {episode_stem(f) for f in EXPECTED_SELECTION}
    for stem in stems:
        matches = [f for f in files if f.endswith(f"-on-{stem}.json")]
        assert len(matches) == 3, (stem, matches)  # one per judge tier
    tier_tokens = {t for t, _ in LADDER_JUDGE_TIERS}
    for path in JUDGE_DIR.glob("judge-*.json"):
        raw = json.loads(path.read_text())
        slot, stem = parse_ladder_judge_filename(path.name)
        assert raw.get("provenance") in ("real-recorded", "placeholder")
        if raw.get("provenance") == "placeholder":
            # Placeholders state the rule + protocol, carry the claim, leak no truth.
            assert slot in tier_tokens
            assert raw["condition"] == "llm-judge-tool-less"
            assert raw["verdict"] is None
            assert "kind" in raw["task"]
            assert f"episode-{stem}.json" == raw["sourceEpisode"]
            blob = json.dumps(raw)
            for truth in TRUTH.values():
                assert str(truth) not in blob, (path.name, truth)


def test_committed_readme_has_no_truth_leak() -> None:
    text = (JUDGE_DIR / "README.md").read_text(encoding="utf-8")
    for truth in TRUTH.values():
        assert str(truth) not in text


def test_build_placeholder_carries_claim_and_hides_truth() -> None:
    claim = {"file": "episode-qwen3-32b-g-17.json", "model": "qwen3:32b",
             "dataset": "hard-count-g", "attempt": "17", "claimed": 767, "rank": 12}
    ph = build_ladder_placeholder(claim, judge_slot="pending", judge_model_hint="claude-opus-4-8")
    assert ph["provenance"] == "placeholder" and ph["status"] == "unrecorded"
    assert ph["claimedRows"] == 767 and ph["intendedJudgeModel"] == "claude-opus-4-8"
    assert ph["sourceEpisode"] == "episode-qwen3-32b-g-17.json"
    assert str(TRUTH["g"]) not in json.dumps(ph)


# --------------------------------------------------------------------------- #
# Scoring math on self-contained synthetic fixtures.
# --------------------------------------------------------------------------- #


def _tmp_ladder(tmp_path: Path):
    """A 2-claim synthetic ladder: two near-miss errors on f (both wrong)."""
    gpu = tmp_path / "gpu"; gpu.mkdir()
    judge = tmp_path / "judges"; judge.mkdir()
    # Two producer errors: 274 and 271 vs truth 273 (|err| 1 and 2).
    _write(gpu, "episode-qwen3-14b-f-13.json", _producer_episode("f", 274, "qwen3:14b"))
    _write(gpu, "episode-qwen3-32b-f-08.json", _producer_episode("f", 271, "qwen3:32b"))
    artifact = tmp_path / "art.json"
    artifact.write_text(json.dumps(_fake_artifact([
        {"file": "episode-qwen3-14b-f-13.json", "model": "qwen3:14b", "dataset": "hard-count-f",
         "attempt": "13", "claimed": 274, "absoluteError": 1, "error": True},
        {"file": "episode-qwen3-32b-f-08.json", "model": "qwen3:32b", "dataset": "hard-count-f",
         "attempt": "08", "claimed": 271, "absoluteError": 2, "error": True},
    ])))
    return gpu, judge, artifact


def _run(gpu, judge, artifact, *, k=2, scale2=None):
    return run_ladder_judge_study(
        pack_dir=PACK_DIR, gpu_study_dir=gpu, judge_dir=judge, plan=PLAN,
        recomputer=RECOMPUTER, artifact_path=artifact, k=k, scale2_comparison=scale2,
    )


def test_scoring_catch_and_recount_accuracy(tmp_path: Path) -> None:
    gpu, judge, artifact = _tmp_ladder(tmp_path)
    # Judge A (sonnet) catches the |err|=1 near-miss and recounts it right; MISSES the
    # |err|=2 near-miss (accepts it). Judge B (haiku) catches both but recounts wrong.
    _write(judge, "judge-claude-sonnet-5-on-qwen3-14b-f-13.json",
           _judge_fixture("qwen3-14b-f-13", "hard-count-f", 274, "reject", recount=273, model="claude-sonnet-5"))
    _write(judge, "judge-claude-sonnet-5-on-qwen3-32b-f-08.json",
           _judge_fixture("qwen3-32b-f-08", "hard-count-f", 271, "accept", model="claude-sonnet-5"))
    _write(judge, "judge-claude-haiku-4-5-on-qwen3-14b-f-13.json",
           _judge_fixture("qwen3-14b-f-13", "hard-count-f", 274, "reject", recount=270, model="claude-haiku-4-5"))
    _write(judge, "judge-claude-haiku-4-5-on-qwen3-32b-f-08.json",
           _judge_fixture("qwen3-32b-f-08", "hard-count-f", 271, "reject", recount=272, model="claude-haiku-4-5"))

    report = _run(gpu, judge, artifact)
    rows = {(r["stem"], r.get("judgeModel")): r for r in report["judgments"] if r.get("judged")}

    # judgeCorrect = rejected exactly the erroneous claims (all are errors here).
    assert rows[("qwen3-14b-f-13", "claude-sonnet-5")]["judgeCorrect"] is True
    assert rows[("qwen3-32b-f-08", "claude-sonnet-5")]["judgeCorrect"] is False  # accepted an error
    assert rows[("qwen3-14b-f-13", "claude-haiku-4-5")]["judgeCorrect"] is True

    by_model = report["comparison"]["llmJudgeByModel"]
    sonnet = by_model["claude-sonnet-5"]
    assert sonnet["errorsJudged"] == 2 and sonnet["caughtOnErrors"] == "1/2"
    assert sonnet["caughtOffByOne"] == "1/1"  # the |err|=1 near-miss
    # All claims are errors -> false-rejection denominator is 0.
    assert sonnet["falseRejectionsOnCorrect"] == "0/0" and sonnet["falseRejectionRateOnCorrect"] is None
    assert sonnet["recountProvided"] == 1 and sonnet["recountAccurate"] == "1/1"

    haiku = by_model["claude-haiku-4-5"]
    assert haiku["caughtOnErrors"] == "2/2"  # rejected both errors
    assert haiku["recountProvided"] == 2 and haiku["recountAccurate"] == "0/2"  # both recounts wrong

    # Side-by-side verifier columns are measured from replay, not asserted.
    assert report["comparison"]["schemaGuard"]["caughtOnErrors"] == "0/2"
    assert report["comparison"]["recomputation"]["caughtOnErrors"] == "2/2"
    assert report["ladderErrors"] == 2 and report["ladderCorrect"] == 0


def test_scoring_skips_placeholders(tmp_path: Path) -> None:
    gpu, judge, artifact = _tmp_ladder(tmp_path)
    _write(judge, "judge-claude-sonnet-5-on-qwen3-14b-f-13.json",
           _judge_fixture("qwen3-14b-f-13", "hard-count-f", 274, "reject", recount=273))
    _write(judge, "judge-pending-on-qwen3-32b-f-08.json",
           build_ladder_placeholder(
               {"file": "episode-qwen3-32b-f-08.json", "model": "qwen3:32b",
                "dataset": "hard-count-f", "attempt": "08", "claimed": 271, "rank": 2},
               judge_slot="pending", judge_model_hint="claude-opus-4-8"))
    report = _run(gpu, judge, artifact)
    rows = {r["file"]: r for r in report["judgments"]}
    assert rows["judge-pending-on-qwen3-32b-f-08.json"]["skipped"] == "unrecorded"
    assert rows["judge-pending-on-qwen3-32b-f-08.json"]["judged"] is False
    assert "judgeVerdict" not in rows["judge-pending-on-qwen3-32b-f-08.json"]
    assert report["comparison"]["llmJudge"]["errorsJudged"] == 1  # only the recorded one


# --------------------------------------------------------------------------- #
# Combined-table math (scale2 4 + ladder 12 = 16).
# --------------------------------------------------------------------------- #


def test_combined_table_merges_scale2_and_ladder_into_sixteen(tmp_path: Path) -> None:
    gpu, judge, artifact = _tmp_ladder(tmp_path)
    _write(judge, "judge-claude-sonnet-5-on-qwen3-14b-f-13.json",
           _judge_fixture("qwen3-14b-f-13", "hard-count-f", 274, "reject", recount=273))
    _write(judge, "judge-claude-sonnet-5-on-qwen3-32b-f-08.json",
           _judge_fixture("qwen3-32b-f-08", "hard-count-f", 271, "reject", recount=273))
    # A synthetic scale2 comparison: 4 available natural errors, sonnet judged 3 of
    # them and caught 2 (missed 1); plus a correct claim it accepted.
    scale2 = {
        "naturalErrors": 4,
        "judgments": [
            {"judged": True, "error": True, "judgeModel": "claude-sonnet-5", "judgeVerdict": "reject"},
            {"judged": True, "error": True, "judgeModel": "claude-sonnet-5", "judgeVerdict": "reject"},
            {"judged": True, "error": True, "judgeModel": "claude-sonnet-5", "judgeVerdict": "accept"},
            {"judged": True, "error": False, "judgeModel": "claude-sonnet-5", "judgeVerdict": "accept"},
            {"judged": False, "error": True},  # an unrecorded scale2 error is not counted
        ],
    }
    report = _run(gpu, judge, artifact, scale2=scale2)
    corpus = report["combined"]["judgedNaturalErrorCorpus"]
    assert corpus["scale2ErrorsAvailable"] == 4
    assert corpus["ladderErrorsAvailable"] == 2  # k=2 in this synthetic run
    assert corpus["totalAvailable"] == 6

    sonnet = report["combined"]["byJudgeModel"]["claude-sonnet-5"]
    # scale2: caught 2 of 3 judged errors; ladder: caught 2 of 2.
    assert sonnet["scale2"]["caughtOnErrors"] == "2/3"
    assert sonnet["ladder"]["caughtOnErrors"] == "2/2"
    assert sonnet["combinedCaughtOnErrors"] == "4/5"  # pooled error catches


def test_committed_grid_replays_without_fabrication() -> None:
    # Over the committed all-placeholder grid, every slot skips honestly and the
    # replayed verifier columns still hold: schema guard 0/12, recomputation 12/12.
    report = run_ladder_judge_study(
        pack_dir=PACK_DIR, gpu_study_dir=GPU_DIR, judge_dir=JUDGE_DIR, plan=PLAN,
        recomputer=RECOMPUTER, artifact_path=ARTIFACT, scale2_comparison=None,
    )
    assert len(report["judgments"]) == 36
    for entry in report["judgments"]:
        if not entry.get("judged"):
            assert "skipped" in entry or "fault" in entry
            continue
        assert entry["judgeCorrect"] == ((entry["judgeVerdict"] == "reject") == entry["error"])
    assert report["comparison"]["schemaGuard"]["caughtOnErrors"] == "0/12"
    assert report["comparison"]["recomputation"]["caughtOnErrors"] == "12/12"
    assert sum(t["slots"] for t in report["judgeRoster"].values()) == 36
