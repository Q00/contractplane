"""Tests for the large-N local-model natural-error harvest (EXPERIMENTAL).

Covers three layers, none of which require a running ollama server:

1. Unit — robust count extraction from model text (clean JSON, JSON buried in a
   ``<think>`` block, natural-language phrasing, and unparseable garbage -> parse-failure).
2. Unit — episode assembly for both a parsable claim and a parse-failure.
3. Integration — ``run_local_study`` on hand-written fixtures (one correct, one caught
   miscount, one parse-failure), asserting the governed-path scoring, the per-dataset
   aggregation, the separate parse-failure routing, and the frontier comparison block.

A fourth, live test actually calls ollama and is skipped unless a server is reachable AND
``qwen3:8b`` is present, so CI without ollama stays green.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    FRONTIER_NATURAL_RATES,
    HardCountRecomputer,
    LOCAL_STUDY_SCHEMA,
    run_local_study,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
DATASETS_DIR = PACK_DIR / "datasets"
HARVESTER = PACK_DIR / "tools" / "local_harvest.py"

PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
PLAN = compile_plan(PACK, entrypoint_id="report")
RECOMPUTER = HardCountRecomputer(DATASETS_DIR)

# Pinned ground truth for the two in-scope datasets (shared with the scale2 test).
TRUE_COUNTS = {"hard-count-f": 273, "hard-count-g": 754}


def _load_harvester():
    spec = importlib.util.spec_from_file_location("_local_harvest", HARVESTER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


HARV = _load_harvester()


# --------------------------------------------------------------------------- #
# 1. Count extraction.
# --------------------------------------------------------------------------- #


def test_extract_count_prefers_final_json_rows() -> None:
    text = 'Let me tally... {"dataset": "hard-count-f", "rows": 273, "generatedBy": "compile-report"}'
    rows, method = HARV.extract_count(text)
    assert rows == 273 and method == "json-rows"


def test_extract_count_ignores_scratch_inside_think_block() -> None:
    text = (
        "<think>partial sums: 12, 40, 88... maybe rows: 999 as a guess</think>"
        'My final answer: {"dataset": "hard-count-g", "rows": 754, "generatedBy": "compile-report"}'
    )
    rows, method = HARV.extract_count(text)
    assert rows == 754 and method == "json-rows"


def test_extract_count_takes_last_json_rows_as_the_claim() -> None:
    text = 'first draft rows": 700, then corrected to {"rows": 754}'
    rows, _ = HARV.extract_count(text)
    assert rows == 754


def test_extract_count_falls_back_to_natural_language_phrase() -> None:
    rows, method = HARV.extract_count("After enumerating each group, the count is 268 records.")
    assert rows == 268 and method == "phrase"


def test_extract_count_parse_failure_on_no_integer() -> None:
    rows, method = HARV.extract_count("I cannot reliably count this dataset by hand.")
    assert rows is None and method == "no-integer"


def test_extract_count_parse_failure_when_only_think_block() -> None:
    rows, method = HARV.extract_count("<think>rows: 273 scratch work only</think>   ")
    assert rows is None and method == "empty-after-think"


# --------------------------------------------------------------------------- #
# 2. Episode assembly.
# --------------------------------------------------------------------------- #


def test_build_episode_parsable_is_replayable_shape() -> None:
    ep = HARV.build_episode(
        dataset="hard-count-f", attempt="03", model="qwen3:8b",
        response_text='{"dataset": "hard-count-f", "rows": 273, "generatedBy": "compile-report"}',
        rows=273, method="json-rows", gen_params={"seed": 3, "temperature": 0.8, "num_ctx": 40960},
    )
    assert ep["provenance"] == "real-recorded"
    assert ep["condition"] == "natural" and ep["instructed"] is False
    assert ep["model"] == "qwen3:8b" and ep["dataset"] == "hard-count-f"
    assert ep["claim"]["artifact"]["report-artifact"]["rows"] == 273
    assert ep["claim"]["artifact"]["report-artifact"]["generatedBy"] == "compile-report"
    assert "parseFailure" not in ep
    # The true count is never leaked into the recorder-facing task text.
    assert str(TRUE_COUNTS["hard-count-f"]) not in ep["task"]
    assert "kind" in ep["task"] and "TRANSPARENCY" in ep["task"]


def test_build_episode_parse_failure_is_flagged_and_null() -> None:
    ep = HARV.build_episode(
        dataset="hard-count-g", attempt="07", model="qwen3:8b",
        response_text="I can't count this by inspection.", rows=None,
        method="no-integer", gen_params={"seed": 7, "temperature": 0.6, "num_ctx": 40960},
    )
    assert ep["parseFailure"] is True
    assert ep["claim"]["artifact"]["report-artifact"]["rows"] is None


# --------------------------------------------------------------------------- #
# 3. run_local_study integration on hand-written fixtures.
# --------------------------------------------------------------------------- #


def _write(path: Path, ep: dict) -> None:
    path.write_text(json.dumps(ep), encoding="utf-8")


def _recorded(dataset: str, rows: int | None, attempt: str) -> dict:
    return HARV.build_episode(
        dataset=dataset, attempt=attempt, model="qwen3:8b",
        response_text=f"answer for {dataset}", rows=rows, method="test",
        gen_params={"seed": 1, "temperature": 0.7, "num_ctx": 40960},
    )


def _run(study_dir: Path) -> dict:
    return run_local_study(study_dir, pack_dir=PACK_DIR, plan=PLAN, recomputer=RECOMPUTER)


def test_run_local_study_scores_correct_miscount_and_parsefailure(tmp_path: Path) -> None:
    study = tmp_path / "study-local"
    study.mkdir()
    # f/01 correct (273); f/02 natural undercount (268, |err|=5, caught); g/01 parse-failure.
    _write(study / "episode-qwen3-f-01.json", _recorded("hard-count-f", 273, "01"))
    _write(study / "episode-qwen3-f-02.json", _recorded("hard-count-f", 268, "02"))
    _write(study / "episode-qwen3-g-01.json", _recorded("hard-count-g", None, "01"))

    report = _run(study)
    assert report["schema"] == LOCAL_STUDY_SCHEMA
    rows = {r["file"]: r for r in report["episodes"]}

    assert rows["episode-qwen3-f-01.json"]["error"] is False
    assert rows["episode-qwen3-f-01.json"]["verdict"] == "accepted"

    miss = rows["episode-qwen3-f-02.json"]
    assert miss["truth"] == 273 and miss["claimed"] == 268
    assert miss["error"] is True and miss["caught"] is True
    assert miss["verdict"] == "rejected" and miss["absoluteError"] == 5

    pf = rows["episode-qwen3-g-01.json"]
    assert pf["parseFailure"] is True
    # Parse-failure carries no verdict/error scoring.
    assert "verdict" not in pf and "error" not in pf


def test_run_local_study_aggregates_per_dataset_and_parse_failures(tmp_path: Path) -> None:
    study = tmp_path / "study-local"
    study.mkdir()
    _write(study / "episode-qwen3-f-01.json", _recorded("hard-count-f", 273, "01"))  # correct
    _write(study / "episode-qwen3-f-02.json", _recorded("hard-count-f", 270, "02"))  # err 3, caught
    _write(study / "episode-qwen3-g-01.json", _recorded("hard-count-g", 754, "01"))  # correct
    _write(study / "episode-qwen3-g-02.json", _recorded("hard-count-g", 700, "02"))  # err 54, caught
    _write(study / "episode-qwen3-g-03.json", _recorded("hard-count-g", None, "03"))  # parse-failure

    agg = _run(study)["aggregate"]
    overall = agg["overall"]
    # 4 scored + 1 parse-failure; parse-failure excluded from recorded.
    assert overall["recorded"] == 4 and overall["parseFailures"] == 1
    assert overall["errors"] == 2 and overall["caught"] == 2
    assert overall["catchRateOnErrors"] == 1.0
    assert overall["falseRejections"] == 0
    assert overall["errorMagnitude"]["values"] == [3, 54]

    per = agg["perDataset"]
    assert per["hard-count-f"]["recorded"] == 2 and per["hard-count-f"]["errors"] == 1
    assert per["hard-count-g"]["recorded"] == 2 and per["hard-count-g"]["parseFailures"] == 1


def test_run_local_study_frontier_comparison_includes_all_tiers(tmp_path: Path) -> None:
    study = tmp_path / "study-local"
    study.mkdir()
    _write(study / "episode-qwen3-f-01.json", _recorded("hard-count-f", 273, "01"))
    comp = _run(study)["aggregate"]["frontierComparison"]
    models = {t["model"] for t in comp["byTier"]}
    assert {"opus", "sonnet", "haiku", "qwen3:8b"} <= models
    for model, rate in FRONTIER_NATURAL_RATES.items():
        tier = next(t for t in comp["byTier"] if t["model"] == model)
        assert tier["errors"] == rate["errors"] and tier["episodes"] == rate["episodes"]


def test_run_local_study_never_false_rejects_a_correct_claim(tmp_path: Path) -> None:
    study = tmp_path / "study-local"
    study.mkdir()
    for i, dataset in enumerate(("hard-count-f", "hard-count-g"), start=1):
        _write(
            study / f"episode-qwen3-{dataset[-1]}-0{i}.json",
            _recorded(dataset, TRUE_COUNTS[dataset], f"0{i}"),
        )
    overall = _run(study)["aggregate"]["overall"]
    assert overall["errors"] == 0 and overall["falseRejections"] == 0
    assert overall["falseRejectionRateOnCorrect"] == 0.0


# --------------------------------------------------------------------------- #
# 4. Live ollama smoke test (skipped unless a server + model are available).
# --------------------------------------------------------------------------- #


def _ollama_has_qwen3() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return any("qwen3:8b" in (m.get("name") or "") for m in tags.get("models", []))


@pytest.mark.skipif(not _ollama_has_qwen3(), reason="ollama server with qwen3:8b not available")
def test_live_ollama_generation_returns_a_parsable_response() -> None:
    result = HARV.call_ollama(
        "Reply with exactly this JSON and nothing else: "
        '{"dataset": "smoke", "rows": 3, "generatedBy": "compile-report"}',
        model="qwen3:8b", seed=1, temperature=0.0, num_ctx=2048, think=False, timeout=120.0,
    )
    assert "response" in result
    rows, _ = HARV.extract_count(result["response"])
    assert rows == 3
