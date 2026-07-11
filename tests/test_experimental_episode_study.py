"""Tests for the experimental multi-family episode study.

EXPERIMENTAL — covers contractplane.experimental.study: the batch runner that
replays recorded producer episodes through the governed kernel path and
aggregates a family x model x condition table across three mechanically
recomputable task families (count, aggregate, filtercount), including honest
skipping of unrecorded placeholder slots.

The tests use only synthetic-smoke fixtures (never citable) plus structural
assertions over the real grid; they never assume how many real slots a separate
recorder agent has filled.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    ChainRecomputer,
    FilterCountRecomputer,
    RecordCountRecomputer,
    SumRecomputer,
    parse_filename,
    run_study,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
STUDY_DIR = PACK_DIR / "episodes" / "study"
STUDY_SMOKE_DIR = PACK_DIR / "episodes" / "study-smoke"
STUDY_SMOKE_METRICS_DIR = PACK_DIR / "episodes" / "study-smoke-metrics"

PLANS = {
    "report": compile_plan(PACK, entrypoint_id="report"),
    "aggregate": compile_plan(PACK, entrypoint_id="aggregate"),
    "filter-count": compile_plan(PACK, entrypoint_id="filter-count"),
}
RECOMPUTER = ChainRecomputer(
    [
        RecordCountRecomputer(DATASETS_DIR),
        SumRecomputer(DATASETS_DIR),
        FilterCountRecomputer(DATASETS_DIR),
    ]
)


def _study(study_dir: Path) -> dict:
    return run_study(study_dir, pack_dir=PACK_DIR, plans=PLANS, recomputer=RECOMPUTER)


def _by_condition(report: dict, family: str) -> dict[str, dict]:
    return {r["condition"]: r for r in report["episodes"] if r["family"] == family}


def test_parse_filename_handles_count_and_family_tokens() -> None:
    assert parse_filename("episode-opus-correct.json") == ("opus", "count", "correct")
    assert parse_filename("episode-haiku-format-violation.json") == ("haiku", "count", "format-violation")
    assert parse_filename("episode-sonnet-aggregate-overclaim.json") == ("sonnet", "aggregate", "overclaim")
    assert parse_filename("episode-opus-filtercount-correct.json") == ("opus", "filtercount", "correct")


def test_count_family_smoke_covers_all_four_conditions() -> None:
    report = _study(STUDY_SMOKE_DIR)
    rows = _by_condition(report, "count")
    assert set(rows) == {"correct", "overclaim", "borderline", "format-violation"}

    assert rows["correct"]["verdict"] == "accepted"
    assert rows["correct"]["verdict_method"] == "recomputation"
    for condition in ("overclaim", "borderline"):
        assert rows[condition]["verdict"] == "rejected"
        assert rows[condition]["schema_gate"] == "pass"
        assert rows[condition]["verdict_method"] == "recomputation"
    assert rows["format-violation"]["schema_gate"] == "fail"
    assert rows["format-violation"]["verdict_method"] == "schema"

    assert all(row["citable"] is False for row in report["episodes"])
    assert report["aggregate"]["table"]["count"]["smoke"]["correct"] == "accepted"


def test_new_families_recompute_sum_and_filter_count() -> None:
    report = _study(STUDY_SMOKE_METRICS_DIR)
    aggregate = _by_condition(report, "aggregate")
    filter_count = _by_condition(report, "filtercount")

    # aggregate: recomputed column total (780 for monthly-metrics).
    assert aggregate["correct"]["checkedField"] == "total"
    assert aggregate["correct"]["claimed"] == aggregate["correct"]["recomputed_truth"] == 780
    assert aggregate["correct"]["verdict"] == "accepted"
    assert aggregate["correct"]["verdict_method"] == "recomputation"
    assert aggregate["overclaim"]["verdict"] == "rejected"
    assert aggregate["overclaim"]["verdict_method"] == "recomputation"

    # filter-count: recomputed count above the flow threshold (4 for sprint-metrics > 10).
    assert filter_count["correct"]["checkedField"] == "matches"
    assert filter_count["correct"]["claimed"] == filter_count["correct"]["recomputed_truth"] == 4
    assert filter_count["correct"]["verdict"] == "accepted"
    assert filter_count["overclaim"]["verdict"] == "rejected"
    assert filter_count["overclaim"]["verdict_method"] == "recomputation"

    by_family = report["aggregate"]["byFamily"]
    assert by_family["aggregate"] == {
        "accepted": 1, "rejected": 1, "skipped": 0, "error": 0, "recorded": 2, "total": 2
    }
    assert by_family["filtercount"] == {
        "accepted": 1, "rejected": 1, "skipped": 0, "error": 0, "recorded": 2, "total": 2
    }


def test_study_groups_three_families_in_one_run(tmp_path: Path) -> None:
    study = tmp_path / "study"
    study.mkdir()
    for source in (STUDY_SMOKE_DIR, STUDY_SMOKE_METRICS_DIR):
        for fixture in source.glob("episode-*.json"):
            shutil.copy(fixture, study / fixture.name)
    report = _study(study)
    by_family = report["aggregate"]["byFamily"]
    assert by_family["count"]["recorded"] == 4
    assert by_family["aggregate"]["recorded"] == 2
    assert by_family["filtercount"]["recorded"] == 2
    assert set(report["aggregate"]["table"]) == {"count", "aggregate", "filtercount"}
    assert report["aggregate"]["counts"]["total"] == 8
    assert report["aggregate"]["counts"]["error"] == 0


def test_study_skips_placeholders_without_fabricating(tmp_path: Path) -> None:
    study = tmp_path / "study"
    study.mkdir()
    recorded = json.loads((STUDY_SMOKE_METRICS_DIR / "episode-smoke-aggregate-correct.json").read_text())
    (study / "episode-opus-aggregate-correct.json").write_text(json.dumps(recorded))
    (study / "episode-opus-aggregate-overclaim.json").write_text(
        json.dumps(
            {
                "schema": "contractplane.dev/experimental/producer-episode/v0",
                "provenance": "placeholder",
                "status": "unrecorded",
                "family": "aggregate",
                "condition": "overclaim",
            }
        )
    )
    report = _study(study)
    counts = report["aggregate"]["counts"]
    assert counts == {"total": 2, "recorded": 1, "skipped": 1, "accepted": 1, "rejected": 0, "error": 0}
    table = report["aggregate"]["table"]["aggregate"]["opus"]
    assert table["correct"] == "accepted"
    assert table["overclaim"] == "skipped"


def test_real_grid_is_enumerated_without_fabrication() -> None:
    # Robust to whichever real slots a separate recorder agent has filled: assert
    # structure and the no-fabrication invariant, not exact accepted/rejected counts.
    report = _study(STUDY_DIR)
    files = sorted(STUDY_DIR.glob("episode-*.json"))
    counts = report["aggregate"]["counts"]
    assert counts["total"] == len(files)
    assert counts["recorded"] + counts["skipped"] + counts["error"] == counts["total"]

    by_family = report["aggregate"]["byFamily"]
    # The committed grid has 12 count slots and 6 slots for each new family.
    assert by_family["count"]["total"] == 12
    assert by_family["aggregate"]["total"] == 6
    assert by_family["filtercount"]["total"] == 6
    assert set(report["aggregate"]["table"]) >= {"count", "aggregate", "filtercount"}
    for entry in report["episodes"]:
        assert entry["model"] and entry["family"] and entry["condition"]
