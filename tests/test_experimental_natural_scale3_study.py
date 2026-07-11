"""Tests for the independent-datasets-per-band scale study (g2/g3/h2/h3).

EXPERIMENTAL — covers the confound fix: each error-prone scale band now holds three
INDEPENDENT datasets (different seeds, same rule and band), so a scale-band effect is
not an artifact of one dataset's identity. Covers the four pinned true counts, the
generator (reused scale2 family + assert_no_shortcut), band-level id independence,
scale_band(), and the power runner's per-band / per-band-model / per-dataset
aggregation via extra_count_grids.

Exact aggregation is checked with self-contained synthetic-smoke episodes so nothing
depends on which real slots a recorder has filled; the committed grid is checked
structurally.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    DATASET_SCALE2_TOKENS,
    DATASET_SCALE3_TOKENS,
    HardCountRecomputer,
    HardSumRecomputer,
    parse_scale_filename,
    run_natural_power_study,
    scale_band,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
SCALE3_DIR = PACK_DIR / "episodes" / "study-natural-scale3"
GENERATOR = PACK_DIR / "scripts" / "generate_hard_scale3_datasets.py"

COUNT_PLAN = compile_plan(PACK, entrypoint_id="report")
AGG_PLAN = compile_plan(PACK, entrypoint_id="aggregate")
COUNT_RECOMPUTER = HardCountRecomputer(DATASETS_DIR)
SUM_RECOMPUTER = HardSumRecomputer(DATASETS_DIR)

# Pinned ground truth for the new independent datasets.
TRUE_COUNTS = {
    "hard-count-g2": 788, "hard-count-g3": 762,
    "hard-count-h2": 1520, "hard-count-h3": 1590,
}
# The full band membership (existing + new), with the existing counts pinned in the
# scale2 test. Bands must contain three independent datasets each.
BANDS = {
    "g": {"hard-count-g": 754, "hard-count-g2": 788, "hard-count-g3": 762},
    "h": {"hard-count-h": 1551, "hard-count-h2": 1520, "hard-count-h3": 1590},
}


def _load_generator():
    spec = importlib.util.spec_from_file_location("_gen_hard_scale3", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _producer_episode(dataset: str, claimed: int, producer: str) -> dict:
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


def _stage():
    return COUNT_PLAN.stages[0]


# --------------------------------------------------------------------------- #
# Pinned true counts, generator, and band independence.
# --------------------------------------------------------------------------- #


def test_recomputer_pins_true_counts_of_the_four_new_datasets() -> None:
    for dataset, truth in TRUE_COUNTS.items():
        got = COUNT_RECOMPUTER.recompute(_stage(), "report-artifact", {"dataset": dataset})
        assert got == {"rows": truth}, dataset


def test_generator_is_deterministic_and_asserts_no_shortcut() -> None:
    gen = _load_generator()
    for name, group_count, seed in gen.SCALE3_SPECS:
        built = gen.build_nested(name, group_count, seed)
        gen.assert_no_shortcut(built)
        assert gen.count_records(built) == TRUE_COUNTS[name]
        committed = (DATASETS_DIR / f"{name}.json").read_text(encoding="utf-8")
        assert committed == gen.render(built), f"{name} drifted from a fresh generation"


def test_each_band_has_three_independent_datasets_with_zero_id_overlap() -> None:
    for band, members in BANDS.items():
        assert len(members) == 3
        id_sets = []
        for dataset, truth in members.items():
            data = json.loads((DATASETS_DIR / f"{dataset}.json").read_text())
            record_ids = [
                item["id"]
                for group in data["groups"]
                for item in group["items"]
                if item.get("kind") == "record"
            ]
            assert len(record_ids) == truth
            id_sets.append(set(record_ids))
        # Independence: the datasets in a band share no record ids.
        for a, b in itertools.combinations(range(3), 2):
            assert not (id_sets[a] & id_sets[b]), band


def test_scale_band_maps_tokens_to_bands() -> None:
    assert scale_band("g2") == "g" and scale_band("g3") == "g" and scale_band("g") == "g"
    assert scale_band("h2") == "h" and scale_band("h") == "h"
    assert scale_band("f") == "f"


def test_parse_scale_filename_with_scale3_tokens() -> None:
    assert parse_scale_filename("episode-opus-g2.json", DATASET_SCALE3_TOKENS) == ("opus", "g2", "hard-count-g2", "1")
    assert parse_scale_filename("episode-haiku-h3.json", DATASET_SCALE3_TOKENS) == ("haiku", "h3", "hard-count-h3", "1")


# --------------------------------------------------------------------------- #
# Power runner: per-band aggregation spans multiple independent datasets.
# --------------------------------------------------------------------------- #


def _power(count_dir, extra, agg_dir):
    return run_natural_power_study(
        pack_dir=PACK_DIR, count_dir=count_dir, count_plan=COUNT_PLAN,
        count_recomputer=COUNT_RECOMPUTER, aggregate_dir=agg_dir, aggregate_plan=AGG_PLAN,
        aggregate_recomputer=SUM_RECOMPUTER, scale_tokens=DATASET_SCALE2_TOKENS,
        extra_count_grids=[(extra, DATASET_SCALE3_TOKENS)],
    )


def test_power_band_pools_independent_datasets_and_models(tmp_path: Path) -> None:
    count_dir = tmp_path / "count"; count_dir.mkdir()
    scale3_dir = tmp_path / "scale3"; scale3_dir.mkdir()
    agg_dir = tmp_path / "agg"; agg_dir.mkdir()
    # band g spans THREE datasets and TWO models: g (opus, correct), g2 (opus, correct),
    # g3 (sonnet, error by 2). band h: h2 (opus, correct).
    _write = lambda d, n, o: (d / n).write_text(json.dumps(o))
    _write(count_dir, "episode-opus-g.json", _producer_episode("hard-count-g", 754, "opus"))
    _write(scale3_dir, "episode-opus-g2.json", _producer_episode("hard-count-g2", 788, "opus"))
    _write(scale3_dir, "episode-sonnet-g3.json", _producer_episode("hard-count-g3", 760, "sonnet"))
    _write(scale3_dir, "episode-opus-h2.json", _producer_episode("hard-count-h2", 1520, "opus"))

    report = _power(count_dir, scale3_dir, agg_dir)
    agg = report["aggregate"]

    assert "g" in report["bands"] and "h" in report["bands"]
    # A band pools its independent datasets.
    assert agg["byBand"]["g"]["N"] == 3 and agg["byBand"]["g"]["errors"] == 1
    assert agg["byBand"]["h"]["N"] == 1 and agg["byBand"]["h"]["errors"] == 0
    # ...and the band spans three genuinely distinct datasets, each visible separately.
    for dataset in ("hard-count-g", "hard-count-g2", "hard-count-g3"):
        assert agg["byDataset"][dataset]["N"] == 1
    # Per band x model is the primary homogeneous unit.
    assert agg["byBandModel"]["g/opus"]["N"] == 2   # g + g2
    assert agg["byBandModel"]["g/sonnet"]["N"] == 1  # g3
    assert agg["byBandModel"]["h/opus"]["N"] == 1
    # The heterogeneous-CI caveat is surfaced, and the pooled band still has a Wilson CI.
    assert "byBand pools" in agg["note"]
    assert set(agg["byBand"]["g"]["errorRateWilson95"]) == {"point", "low", "high"}
    # The g3 miscount was caught by recomputation.
    g3_row = next(e for e in report["episodes"] if e["dataset"] == "hard-count-g3")
    assert g3_row["error"] is True and g3_row["caught"] is True and g3_row["truth"] == 762


# --------------------------------------------------------------------------- #
# Committed grid.
# --------------------------------------------------------------------------- #


def test_committed_scale3_grid_is_twelve_placeholder_slots() -> None:
    files = sorted(p.name for p in SCALE3_DIR.glob("episode-*.json"))
    expected = [
        f"episode-{m}-{s}.json"
        for m in ("haiku", "opus", "sonnet")
        for s in ("g2", "g3", "h2", "h3")
    ]
    assert files == sorted(expected)
    assert len(files) == 12
    for path in SCALE3_DIR.glob("episode-*.json"):
        raw = json.loads(path.read_text())
        assert raw["condition"] == "natural" and raw["instructed"] is False
        assert raw["band"] == scale_band(raw["scale"])
        assert "kind" in raw["task"]
        for truth in TRUE_COUNTS.values():
            assert str(truth) not in raw["task"]  # never told the answer


def test_committed_power_run_includes_scale3_band_datasets() -> None:
    report = run_natural_power_study(
        pack_dir=PACK_DIR,
        count_dir=PACK_DIR / "episodes" / "study-natural-scale2",
        count_plan=COUNT_PLAN, count_recomputer=COUNT_RECOMPUTER,
        aggregate_dir=PACK_DIR / "episodes" / "study-natural-aggregate",
        aggregate_plan=AGG_PLAN, aggregate_recomputer=SUM_RECOMPUTER,
        extra_count_grids=[(SCALE3_DIR, DATASET_SCALE3_TOKENS)],
    )
    # The g and h bands now include the independent g2/g3/h2/h3 datasets.
    assert set(report["datasets"]) >= {
        "hard-count-g", "hard-count-g2", "hard-count-g3",
        "hard-count-h", "hard-count-h2", "hard-count-h3",
    }
    assert {"g", "h"} <= set(report["aggregate"]["byBand"])
    # 21 scale2 count + 12 scale3 + 6 aggregate = 39 enumerated episodes.
    assert len(report["episodes"]) == 39
    for entry in report["episodes"]:
        if "skipped" in entry or "fault" in entry:
            continue
        assert entry["caught"] == bool(entry["error"] and entry["verdict"] == "rejected")


def test_committed_power_run_pins_per_model_counts_and_fisher_pvalues() -> None:
    # With every natural slot recorded, per-model error counts are 2/13, 4/13, 7/13,
    # and the three pairwise Fisher exact tests are all non-significant. These numbers
    # are cited in the paper, so they are pinned here.
    report = run_natural_power_study(
        pack_dir=PACK_DIR,
        count_dir=PACK_DIR / "episodes" / "study-natural-scale2",
        count_plan=COUNT_PLAN, count_recomputer=COUNT_RECOMPUTER,
        aggregate_dir=PACK_DIR / "episodes" / "study-natural-aggregate",
        aggregate_plan=AGG_PLAN, aggregate_recomputer=SUM_RECOMPUTER,
        extra_count_grids=[(SCALE3_DIR, DATASET_SCALE3_TOKENS)],
    )
    by_model = report["aggregate"]["byModel"]
    assert (by_model["opus"]["errors"], by_model["opus"]["N"]) == (2, 13)
    assert (by_model["sonnet"]["errors"], by_model["sonnet"]["N"]) == (4, 13)
    assert (by_model["haiku"]["errors"], by_model["haiku"]["N"]) == (7, 13)

    fisher = report["aggregate"]["pairwiseModelErrorFisher"]
    assert fisher["opus_vs_sonnet"]["pValueTwoSided"] == 0.64472
    assert fisher["haiku_vs_opus"]["pValueTwoSided"] == 0.096842
    assert fisher["haiku_vs_sonnet"]["pValueTwoSided"] == 0.428308
    assert all(pair["pValueTwoSided"] > 0.05 for pair in fisher.values())
