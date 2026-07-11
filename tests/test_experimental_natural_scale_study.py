"""Tests for the experimental spontaneous-error SCALE study.

EXPERIMENTAL — covers the scale extension of contractplane.experimental.natural_study:
the three scaled hard datasets (hard-count-c/d/e), the deterministic checked-in
generator that produces them, ``parse_scale_filename``, and ``run_natural_scale_study``
which replays the ``episode-<model>-<c|d|e>.json`` grid through the governed kernel
path and aggregates natural error / catch / false-rejection rates per scale and per
model, plus per-episode absolute error.

The three true record counts are pinned here so a drift in the datasets, the
generator, or the counting rule fails a test. Recorder-facing episodes never carry
these counts; only this orchestrator-side test does.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    HardCountRecomputer,
    parse_scale_filename,
    run_natural_scale_study,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
SCALE_DIR = PACK_DIR / "episodes" / "study-natural-scale"
GENERATOR = PACK_DIR / "scripts" / "generate_hard_scale_datasets.py"

PLAN = compile_plan(PACK, entrypoint_id="report")
RECOMPUTER = HardCountRecomputer(DATASETS_DIR)

# Pinned ground truth. Deliberately non-round so a genuine tool-less reader must
# actually count. These match the generator's exact record targets.
TRUE_COUNTS = {"hard-count-c": 307, "hard-count-d": 794, "hard-count-e": 1523}


def _load_generator():
    spec = importlib.util.spec_from_file_location("_gen_hard_scale", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _stage():
    return PLAN.stages[0]


def _recorded_scale_episode(dataset: str, claimed_rows: int, model: str) -> dict:
    return {
        "schema": "contractplane.dev/experimental/producer-episode/v0",
        "provenance": "synthetic-smoke",
        "condition": "natural",
        "instructed": False,
        "adversarial": False,
        "model": model,
        "dataset": dataset,
        "flow": "report",
        "input": {"dataset": dataset},
        "task": "SYNTHETIC SMOKE FIXTURE (not a real model output; do not cite).",
        "response": f"SYNTHETIC SMOKE natural scale attempt. Claimed rows={claimed_rows}.",
        "claim": {
            "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": claimed_rows},
            "artifact": {
                "report-artifact": {
                    "dataset": dataset,
                    "rows": claimed_rows,
                    "generatedBy": "compile-report",
                }
            },
        },
    }


# --------------------------------------------------------------------------- #
# Datasets, generator, and recomputer: pinned exactly.
# --------------------------------------------------------------------------- #


def test_recomputer_pins_true_counts_of_all_three_scale_datasets() -> None:
    for dataset, truth in TRUE_COUNTS.items():
        got = RECOMPUTER.recompute(_stage(), "report-artifact", {"dataset": dataset})
        assert got == {"rows": truth}, dataset


def test_scale_counts_grow_and_keep_the_same_rule_and_trap_density() -> None:
    prev = 0
    for dataset in ("hard-count-c", "hard-count-d", "hard-count-e"):
        data = json.loads((DATASETS_DIR / f"{dataset}.json").read_text())
        assert data["structure"] == "nested-groups"
        by_hand = sum(
            1
            for group in data["groups"]
            for item in group["items"]
            if item.get("kind") == "record"
        )
        assert by_hand == TRUE_COUNTS[dataset]
        assert by_hand > prev  # scale strictly increases c < d < e
        prev = by_hand
        # The record-shaped metadata trap is present at every scale.
        assert any(
            item.get("kind") == "metadata"
            for group in data["groups"]
            for item in group["items"]
        )


def test_generator_is_deterministic_and_committed_files_match() -> None:
    gen = _load_generator()
    for name, target in gen.SCALE_SPECS:
        built = gen.build_nested(name, target)
        assert gen.count_records(built) == target
        committed = (DATASETS_DIR / f"{name}.json").read_text(encoding="utf-8")
        assert committed == gen.render(built), f"{name} drifted from a fresh generation"
    # The generator's own targets are exactly what this test pins.
    assert dict(gen.SCALE_SPECS) == TRUE_COUNTS


# --------------------------------------------------------------------------- #
# Filename parsing.
# --------------------------------------------------------------------------- #


def test_parse_scale_filename_resolves_model_scale_dataset() -> None:
    # First-attempt slots carry no attempt token -> attempt "1".
    assert parse_scale_filename("episode-opus-c.json") == ("opus", "c", "hard-count-c", "1")
    assert parse_scale_filename("episode-sonnet-d.json") == ("sonnet", "d", "hard-count-d", "1")
    assert parse_scale_filename("episode-haiku-e.json") == ("haiku", "e", "hard-count-e", "1")


# --------------------------------------------------------------------------- #
# Runner: catches natural errors, records absolute error, aggregates by scale.
# --------------------------------------------------------------------------- #


def _run(study_dir: Path) -> dict:
    return run_natural_scale_study(study_dir, pack_dir=PACK_DIR, plan=PLAN, recomputer=RECOMPUTER)


def test_runner_records_absolute_error_and_catches_a_natural_miscount(tmp_path: Path) -> None:
    study = tmp_path / "study"
    study.mkdir()
    # opus/c: correct (307). haiku/e: a natural under-count (1500 != 1523, |err|=23).
    (study / "episode-opus-c.json").write_text(
        json.dumps(_recorded_scale_episode("hard-count-c", 307, "claude-opus-4-8"))
    )
    (study / "episode-haiku-e.json").write_text(
        json.dumps(_recorded_scale_episode("hard-count-e", 1500, "claude-haiku-4-5"))
    )
    report = _run(study)
    rows = {r["file"]: r for r in report["episodes"]}

    correct = rows["episode-opus-c.json"]
    assert correct["error"] is False and correct["caught"] is False
    assert correct["verdict"] == "accepted" and correct["verdict_method"] == "recomputation"
    assert correct["absoluteError"] == 0
    assert correct["scale"] == "c" and correct["dataset"] == "hard-count-c"

    miss = rows["episode-haiku-e.json"]
    assert miss["truth"] == 1523 and miss["claimed"] == 1500
    assert miss["error"] is True and miss["caught"] is True
    assert miss["verdict"] == "rejected" and miss["verdict_method"] == "recomputation"
    assert miss["absoluteError"] == 23


def test_runner_aggregates_per_scale_and_per_model(tmp_path: Path) -> None:
    study = tmp_path / "study"
    study.mkdir()
    # scale c: opus correct.                       -> c: 0 errors
    (study / "episode-opus-c.json").write_text(
        json.dumps(_recorded_scale_episode("hard-count-c", 307, "claude-opus-4-8"))
    )
    # scale d: sonnet errs by 5 (caught).          -> d: 1 error, caught, MAE 5
    (study / "episode-sonnet-d.json").write_text(
        json.dumps(_recorded_scale_episode("hard-count-d", 789, "claude-sonnet-5"))
    )
    # scale e: haiku errs by 40, opus errs by 10.  -> e: 2 errors, caught, MAE 25
    (study / "episode-haiku-e.json").write_text(
        json.dumps(_recorded_scale_episode("hard-count-e", 1483, "claude-haiku-4-5"))
    )
    (study / "episode-opus-e.json").write_text(
        json.dumps(_recorded_scale_episode("hard-count-e", 1513, "claude-opus-4-8"))
    )
    report = _run(study)
    agg = report["aggregate"]

    overall = agg["overall"]
    assert overall["recorded"] == 4
    assert overall["errors"] == 3 and overall["caught"] == 3 and overall["missed"] == 0
    assert overall["naturalErrorRate"] == 0.75
    assert overall["catchRateOnErrors"] == 1.0
    assert overall["falseRejections"] == 0 and overall["falseRejectionRateOnCorrect"] == 0.0
    assert overall["meanAbsoluteError"] == round((5 + 40 + 10) / 3, 4)

    per_scale = agg["perScale"]
    assert per_scale["c"]["errors"] == 0
    assert per_scale["c"]["naturalErrorRate"] == 0.0
    assert per_scale["c"]["catchRateOnErrors"] is None  # no errors -> null, not fabricated
    assert per_scale["c"]["meanAbsoluteError"] is None
    assert per_scale["d"]["errors"] == 1 and per_scale["d"]["meanAbsoluteError"] == 5
    assert per_scale["e"]["errors"] == 2 and per_scale["e"]["caught"] == 2
    assert per_scale["e"]["meanAbsoluteError"] == 25.0
    assert per_scale["e"]["catchRateOnErrors"] == 1.0

    per_model = agg["perModel"]
    assert per_model["opus"]["recorded"] == 2 and per_model["opus"]["errors"] == 1
    assert per_model["haiku"]["errors"] == 1 and per_model["haiku"]["catchRateOnErrors"] == 1.0


def test_runner_skips_scale_placeholders_without_fabricating(tmp_path: Path) -> None:
    study = tmp_path / "study"
    study.mkdir()
    (study / "episode-opus-c.json").write_text(
        json.dumps(_recorded_scale_episode("hard-count-c", 307, "claude-opus-4-8"))
    )
    (study / "episode-opus-d.json").write_text(
        json.dumps(
            {
                "schema": "contractplane.dev/experimental/producer-episode/v0",
                "provenance": "placeholder",
                "status": "unrecorded",
                "condition": "natural",
                "instructed": False,
                "dataset": "hard-count-d",
                "scale": "d",
            }
        )
    )
    report = _run(study)
    rows = {r["file"]: r for r in report["episodes"]}
    assert rows["episode-opus-d.json"]["skipped"] == "unrecorded"
    assert "claimed" not in rows["episode-opus-d.json"]
    overall = report["aggregate"]["overall"]
    assert overall["recorded"] == 1 and overall["skipped"] == 1


# --------------------------------------------------------------------------- #
# The committed grid: 9 real slots, enumerated without fabrication.
# --------------------------------------------------------------------------- #


def test_committed_scale_grid_is_the_nine_slot_design() -> None:
    files = sorted(p.name for p in SCALE_DIR.glob("episode-*.json"))
    expected = [
        f"episode-{model}-{scale}.json"
        for model in ("haiku", "opus", "sonnet")
        for scale in ("c", "d", "e")
    ]
    assert files == sorted(expected)
    assert len(files) == 9


def test_committed_scale_grid_replays_without_fabrication_and_states_the_rule() -> None:
    report = _run(SCALE_DIR)
    assert report["schema"] == "contractplane.dev/experimental/natural-scale-study/v0"
    assert report["condition"] == "natural" and report["instructed"] is False
    assert report["scales"] == ["c", "d", "e"]
    assert len(report["episodes"]) == 9
    overall = report["aggregate"]["overall"]
    # No real recordings yet: every slot skips honestly, nothing is fabricated.
    assert overall["skipped"] + overall["recorded"] + overall["fault"] == 9

    for path in SCALE_DIR.glob("episode-*.json"):
        raw = json.loads(path.read_text())
        assert raw["condition"] == "natural" and raw["instructed"] is False
        assert "kind" in raw["task"]  # the nested-groups rule is stated
        for truth in TRUE_COUNTS.values():
            assert str(truth) not in raw["task"]  # never told the answer
