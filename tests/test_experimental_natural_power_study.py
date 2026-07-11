"""Tests for the merged spontaneous-error POWER study.

EXPERIMENTAL — covers the statistical-power expansion of the natural study:
the HardSumRecomputer for the aggregate (sum) family, the Wilson 95% binomial CI,
parse_scale_filename's -rN repetition suffix, and run_natural_power_study, which
merges the shortcut-closed counting grid (f/g/h incl. repetitions) with the
aggregate grid (g/h) and aggregates per family / scale / model.

The true sums of hard-count-g/h are pinned here (orchestrator-side only); the
Wilson CI is pinned against a hand-computed reference. Exact aggregation is checked
with synthetic-smoke fixtures so the assertions never depend on which real slots a
separate recorder agent has filled; the committed grids are only checked
structurally and for the no-fabrication invariant.
"""

from __future__ import annotations

import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    DATASET_SCALE2_TOKENS,
    HardCountRecomputer,
    HardSumRecomputer,
    parse_scale_filename,
    run_natural_power_study,
    wilson_interval,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
SCALE2_DIR = PACK_DIR / "episodes" / "study-natural-scale2"
AGG_DIR = PACK_DIR / "episodes" / "study-natural-aggregate"

COUNT_PLAN = compile_plan(PACK, entrypoint_id="report")
AGG_PLAN = compile_plan(PACK, entrypoint_id="aggregate")
COUNT_RECOMPUTER = HardCountRecomputer(DATASETS_DIR)
SUM_RECOMPUTER = HardSumRecomputer(DATASETS_DIR)

# Pinned ground truth. Record counts stay 273/754/1551 (see the scale2 test); the
# aggregate family sums the per-record integer `value` field.
TRUE_COUNTS = {"hard-count-g": 754, "hard-count-h": 1551}
TRUE_SUMS = {"hard-count-g": 37496, "hard-count-h": 77874}


def _stage(plan):
    return plan.stages[0]


def _count_episode(dataset: str, claimed: int, model: str) -> dict:
    return {
        "schema": "contractplane.dev/experimental/producer-episode/v0",
        "provenance": "synthetic-smoke",
        "condition": "natural", "instructed": False, "adversarial": False,
        "model": model, "dataset": dataset, "flow": "report",
        "input": {"dataset": dataset},
        "task": "SYNTHETIC SMOKE FIXTURE (not a real model output; do not cite).",
        "response": f"SYNTHETIC SMOKE count. rows={claimed}.",
        "claim": {
            "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": claimed},
            "artifact": {"report-artifact": {"dataset": dataset, "rows": claimed, "generatedBy": "compile-report"}},
        },
    }


def _sum_episode(dataset: str, claimed: int, model: str) -> dict:
    return {
        "schema": "contractplane.dev/experimental/producer-episode/v0",
        "provenance": "synthetic-smoke",
        "condition": "natural", "instructed": False, "adversarial": False,
        "model": model, "dataset": dataset, "flow": "aggregate",
        "input": {"dataset": dataset},
        "task": "SYNTHETIC SMOKE FIXTURE (not a real model output; do not cite).",
        "response": f"SYNTHETIC SMOKE sum. total={claimed}.",
        "claim": {
            "outputs": {"artifact": "evidence/aggregate.aggregate-artifact.json", "total": claimed},
            "artifact": {"aggregate-artifact": {"dataset": dataset, "total": claimed, "generatedBy": "aggregate-metric"}},
        },
    }


# --------------------------------------------------------------------------- #
# HardSumRecomputer: pinned true sums.
# --------------------------------------------------------------------------- #


def test_sum_recomputer_pins_true_sums_of_g_and_h() -> None:
    for dataset, total in TRUE_SUMS.items():
        got = SUM_RECOMPUTER.recompute(_stage(AGG_PLAN), "aggregate-artifact", {"dataset": dataset})
        assert got == {"total": total}, dataset


def test_sum_recomputer_matches_a_hand_pass_and_ignores_metadata() -> None:
    for dataset, total in TRUE_SUMS.items():
        data = json.loads((DATASETS_DIR / f"{dataset}.json").read_text())
        by_hand = sum(
            item["value"]
            for group in data["groups"]
            for item in group["items"]
            if item.get("kind") == "record"
        )
        assert by_hand == total
        # Metadata items carry no value and are excluded from the sum.
        assert all(
            "value" not in item
            for group in data["groups"]
            for item in group["items"]
            if item.get("kind") == "metadata"
        )


def test_sum_recomputer_ignores_other_evidence_and_unknown_datasets() -> None:
    assert SUM_RECOMPUTER.recompute(_stage(AGG_PLAN), "report-artifact", {"dataset": "hard-count-g"}) is None
    assert SUM_RECOMPUTER.recompute(_stage(AGG_PLAN), "aggregate-artifact", {"dataset": "nope"}) is None


# --------------------------------------------------------------------------- #
# Wilson interval and -rN parsing.
# --------------------------------------------------------------------------- #


def test_wilson_interval_matches_reference_and_edges() -> None:
    # 2/10 at 95%: hand-computed Wilson bounds.
    assert wilson_interval(2, 10) == (0.0567, 0.5098)
    # No sample -> no interval (never fabricated as 0/1).
    assert wilson_interval(0, 0) == (None, None)
    # Degenerate proportions stay inside [0, 1] and bracket the point estimate.
    low0, high0 = wilson_interval(0, 8)
    assert low0 == 0.0 and 0.0 < high0 < 1.0
    low1, high1 = wilson_interval(8, 8)
    assert high1 == 1.0 and 0.0 < low1 < 1.0


def test_parse_scale_filename_repetition_suffix() -> None:
    assert parse_scale_filename("episode-opus-g.json", DATASET_SCALE2_TOKENS) == ("opus", "g", "hard-count-g", "1")
    assert parse_scale_filename("episode-opus-g-r2.json", DATASET_SCALE2_TOKENS) == ("opus", "g", "hard-count-g", "2")
    assert parse_scale_filename("episode-haiku-h-r3.json", DATASET_SCALE2_TOKENS) == ("haiku", "h", "hard-count-h", "3")


# --------------------------------------------------------------------------- #
# The aggregate family replays through the governed path.
# --------------------------------------------------------------------------- #


def _power(count_dir: Path, aggregate_dir: Path) -> dict:
    return run_natural_power_study(
        pack_dir=PACK_DIR,
        count_dir=count_dir,
        count_plan=COUNT_PLAN,
        count_recomputer=COUNT_RECOMPUTER,
        aggregate_dir=aggregate_dir,
        aggregate_plan=AGG_PLAN,
        aggregate_recomputer=SUM_RECOMPUTER,
        scale_tokens=DATASET_SCALE2_TOKENS,
    )


def test_aggregate_family_catches_a_natural_sum_error(tmp_path: Path) -> None:
    count_dir = tmp_path / "count"; count_dir.mkdir()
    agg_dir = tmp_path / "agg"; agg_dir.mkdir()
    # correct sum for g -> accepted; a short sum for h -> caught.
    (agg_dir / "episode-opus-g.json").write_text(json.dumps(_sum_episode("hard-count-g", TRUE_SUMS["hard-count-g"], "claude-opus-4-8")))
    (agg_dir / "episode-haiku-h.json").write_text(json.dumps(_sum_episode("hard-count-h", 77000, "claude-haiku-4-5")))
    report = _power(count_dir, agg_dir)
    rows = {r["file"]: r for r in report["episodes"] if r["family"] == "aggregate"}

    correct = rows["episode-opus-g.json"]
    assert correct["checkedField"] == "total"
    assert correct["claimed"] == correct["truth"] == TRUE_SUMS["hard-count-g"]
    assert correct["error"] is False and correct["verdict"] == "accepted"
    assert correct["verdict_method"] == "recomputation" and correct["caught"] is False

    miss = rows["episode-haiku-h.json"]
    assert miss["truth"] == TRUE_SUMS["hard-count-h"] and miss["claimed"] == 77000
    assert miss["error"] is True and miss["caught"] is True
    assert miss["absoluteError"] == TRUE_SUMS["hard-count-h"] - 77000


# --------------------------------------------------------------------------- #
# Merged aggregation across families / scales / models.
# --------------------------------------------------------------------------- #


def test_power_study_merges_families_and_aggregates_with_ci(tmp_path: Path) -> None:
    count_dir = tmp_path / "count"; count_dir.mkdir()
    agg_dir = tmp_path / "agg"; agg_dir.mkdir()
    # counting: g attempt1 correct, g-r2 error(4), h error(151) -> 2 errors / 3
    (count_dir / "episode-opus-g.json").write_text(json.dumps(_count_episode("hard-count-g", TRUE_COUNTS["hard-count-g"], "claude-opus-4-8")))
    (count_dir / "episode-opus-g-r2.json").write_text(json.dumps(_count_episode("hard-count-g", 750, "claude-opus-4-8")))
    (count_dir / "episode-haiku-h.json").write_text(json.dumps(_count_episode("hard-count-h", 1400, "claude-haiku-4-5")))
    # aggregate: g correct, h error(874) -> 1 error / 2
    (agg_dir / "episode-sonnet-g.json").write_text(json.dumps(_sum_episode("hard-count-g", TRUE_SUMS["hard-count-g"], "claude-sonnet-5")))
    (agg_dir / "episode-haiku-h.json").write_text(json.dumps(_sum_episode("hard-count-h", 77000, "claude-haiku-4-5")))
    report = _power(count_dir, agg_dir)
    agg = report["aggregate"]

    assert report["families"] == ["count", "aggregate"]
    overall = agg["overall"]
    assert overall["N"] == 5 and overall["errors"] == 3 and overall["caught"] == 3
    assert overall["falseRejections"] == 0
    # Wilson CI present and brackets the point estimate.
    ci = overall["errorRateWilson95"]
    assert ci["point"] == round(3 / 5, 4)
    assert ci["low"] is not None and ci["low"] <= ci["point"] <= ci["high"]

    by_family = agg["byFamily"]
    assert by_family["count"]["N"] == 3 and by_family["count"]["errors"] == 2
    assert by_family["aggregate"]["N"] == 2 and by_family["aggregate"]["errors"] == 1
    # Error-magnitude distribution is reported per group.
    count_mag = by_family["count"]["errorMagnitude"]
    assert count_mag["values"] == [4, 151] and count_mag["max"] == 151 and count_mag["min"] == 4

    by_scale = agg["byScale"]
    assert set(by_scale) == {"g", "h"}
    assert by_scale["g"]["N"] == 3  # g count x2 + g aggregate x1
    assert by_scale["h"]["N"] == 2

    by_model = agg["byModel"]
    assert by_model["opus"]["N"] == 2 and by_model["haiku"]["N"] == 2 and by_model["sonnet"]["N"] == 1

    assert set(agg["byFamilyScale"]) == {"count/g", "count/h", "aggregate/g", "aggregate/h"}
    assert agg["byFamilyScale"]["count/g"]["N"] == 2


def test_power_study_skips_placeholders_without_fabricating(tmp_path: Path) -> None:
    count_dir = tmp_path / "count"; count_dir.mkdir()
    agg_dir = tmp_path / "agg"; agg_dir.mkdir()
    (count_dir / "episode-opus-g.json").write_text(json.dumps(_count_episode("hard-count-g", TRUE_COUNTS["hard-count-g"], "claude-opus-4-8")))
    (count_dir / "episode-opus-g-r2.json").write_text(json.dumps(
        {"schema": "contractplane.dev/experimental/producer-episode/v0", "provenance": "placeholder",
         "status": "unrecorded", "condition": "natural", "instructed": False, "dataset": "hard-count-g", "scale": "g"}
    ))
    report = _power(count_dir, agg_dir)
    rows = {r["file"]: r for r in report["episodes"]}
    assert rows["episode-opus-g-r2.json"]["skipped"] == "unrecorded"
    assert "claimed" not in rows["episode-opus-g-r2.json"]
    overall = report["aggregate"]["overall"]
    assert overall["N"] == 1 and overall["skipped"] == 1
    # Empty-denominator CI is null, never fabricated.
    assert overall["errorRateWilson95"]["point"] in (0.0, None)


# --------------------------------------------------------------------------- #
# Committed grids: enumerated without fabrication (robust to recorder progress).
# --------------------------------------------------------------------------- #


def test_committed_grids_have_the_repetition_and_aggregate_slots() -> None:
    scale2 = sorted(p.name for p in SCALE2_DIR.glob("episode-*.json"))
    # 9 base f/g/h + 12 repetition slots (g/h x r2/r3 x 3 models) = 21.
    reps = [f"episode-{m}-{s}-r{n}.json" for m in ("opus", "sonnet", "haiku") for s in ("g", "h") for n in ("2", "3")]
    assert set(reps) <= set(scale2)
    assert len([n for n in scale2 if "-r" in n]) == 12
    assert len(scale2) == 21

    agg = sorted(p.name for p in AGG_DIR.glob("episode-*.json"))
    expected_agg = [f"episode-{m}-{s}.json" for m in ("opus", "sonnet", "haiku") for s in ("g", "h")]
    assert agg == sorted(expected_agg)
    assert len(agg) == 6


def test_committed_power_study_replays_without_fabrication() -> None:
    report = _power(SCALE2_DIR, AGG_DIR)
    assert report["families"] == ["count", "aggregate"]
    # 21 counting + 6 aggregate episodes enumerated.
    assert len(report["episodes"]) == 27
    overall = report["aggregate"]["overall"]
    assert overall["N"] + overall["skipped"] + overall["fault"] == 27
    # No fabrication: every recorded row has a recomputed truth, and correctness of
    # 'caught' is internally consistent.
    for entry in report["episodes"]:
        if "skipped" in entry or "fault" in entry:
            continue
        assert entry["truth"] is not None
        assert entry["caught"] == bool(entry["error"] and entry["verdict"] == "rejected")
    # Aggregate slots state the summation rule and never leak the true total.
    for path in AGG_DIR.glob("episode-*.json"):
        raw = json.loads(path.read_text())
        if raw.get("provenance") == "placeholder":
            assert "value" in raw["task"]
            for total in TRUE_SUMS.values():
                assert str(total) not in raw["task"]
