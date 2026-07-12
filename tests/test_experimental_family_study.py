"""Tests for the multi-model family study + shared harvest protocol (EXPERIMENTAL).

Two guarantees for the parallel harvest tracks (Track A: OpenAI family, Track B:
GPU local ladder):

1. **Prompt drift guard** — the shared ``tools/harvest_protocol.py`` constants are
   byte-identical to the ones inside the already-executed ``tools/local_harvest.py``.
   If either copy changes, this fails: a changed prompt is a NEW eval condition and
   must be introduced deliberately, never silently.
2. **run_family_study** — replays a mixed-model fixture grid through the governed
   path and aggregates per model and per model x dataset, with a family-aware
   frontier comparison. Placeholders skip honestly; parse-failures route separately.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    FRONTIER_NATURAL_RATES,
    HardCountRecomputer,
    run_family_study,
)
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "examples" / "governed-run"
TOOLS = PACK_DIR / "tools"

PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
PLAN = compile_plan(PACK, entrypoint_id="report")
RECOMPUTER = HardCountRecomputer(PACK_DIR / "datasets")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


HARV = _load("local_harvest")
PROTO = _load("harvest_protocol")


# --------------------------------------------------------------------------- #
# 1. Prompt drift guard.
# --------------------------------------------------------------------------- #


def test_shared_task_template_matches_executed_harvester_verbatim() -> None:
    assert PROTO.COUNT_TASK_TEMPLATE == HARV.TASK_TEMPLATE


def test_shared_prompt_builder_matches_executed_harvester_byte_for_byte() -> None:
    sample = '{"groups": []}'
    for dataset in ("hard-count-f", "hard-count-g", "hard-count-h2"):
        assert PROTO.build_task(dataset) == HARV.build_task(dataset)
        assert PROTO.build_prompt(dataset, sample) == HARV.build_prompt(dataset, sample)


# --------------------------------------------------------------------------- #
# 2. run_family_study on mixed-model fixtures.
# --------------------------------------------------------------------------- #


def _write(path: Path, ep: dict) -> None:
    path.write_text(json.dumps(ep), encoding="utf-8")


def _recorded(model: str, dataset: str, rows: int | None, attempt: str) -> dict:
    return HARV.build_episode(
        dataset=dataset, attempt=attempt, model=model,
        response_text=f"answer for {dataset}", rows=rows, method="test",
        gen_params={"seed": 1, "temperature": 0.7, "num_ctx": 40960},
    )


def test_run_family_study_aggregates_per_model_and_dataset(tmp_path: Path) -> None:
    study = tmp_path / "study-openai"
    study.mkdir()
    # luna: correct on f, miscount on g (caught). terra: miscount on f, parse-failure on g.
    _write(study / "episode-luna-f-01.json", _recorded("luna-x", "hard-count-f", 273, "01"))
    _write(study / "episode-luna-g-01.json", _recorded("luna-x", "hard-count-g", 700, "01"))
    _write(study / "episode-terra-f-01.json", _recorded("terra-x", "hard-count-f", 268, "01"))
    _write(study / "episode-terra-g-01.json", _recorded("terra-x", "hard-count-g", None, "01"))
    # An unrecorded placeholder must skip honestly, never score.
    _write(
        study / "episode-sol-f-01.json",
        {"provenance": "placeholder", "status": "unrecorded", "model": "sol-x",
         "dataset": "hard-count-f"},
    )

    report = run_family_study(
        study, pack_dir=PACK_DIR, plan=PLAN, recomputer=RECOMPUTER, family="openai"
    )
    assert report["family"] == "openai"

    rows = {r["file"]: r for r in report["episodes"]}
    assert rows["episode-sol-f-01.json"]["skipped"] == "unrecorded"
    assert rows["episode-luna-g-01.json"]["error"] is True
    assert rows["episode-luna-g-01.json"]["caught"] is True

    agg = report["aggregate"]
    per_model = agg["perModel"]
    assert per_model["luna-x"]["recorded"] == 2 and per_model["luna-x"]["errors"] == 1
    assert per_model["terra-x"]["recorded"] == 1 and per_model["terra-x"]["errors"] == 1
    assert per_model["terra-x"]["parseFailures"] == 1
    # Placeholder model contributes no scored rows.
    assert per_model.get("sol-x", {"recorded": 0})["recorded"] == 0

    pmd = agg["perModelDataset"]
    assert pmd["luna-x"]["hard-count-f"]["errors"] == 0
    assert pmd["luna-x"]["hard-count-g"]["errors"] == 1
    assert pmd["terra-x"]["hard-count-f"]["errors"] == 1

    comp = agg["frontierComparison"]
    tiers = {t["model"]: t for t in comp["byTier"]}
    for model in FRONTIER_NATURAL_RATES:
        assert tiers[model]["tier"] == "frontier"
    assert tiers["luna-x"]["tier"] == "openai"
    assert tiers["terra-x"]["tier"] == "openai"
    assert tiers["luna-x"]["naturalErrorRate"] == 0.5


def test_run_family_study_never_false_rejects_correct_claims(tmp_path: Path) -> None:
    study = tmp_path / "study-openai"
    study.mkdir()
    _write(study / "episode-luna-f-01.json", _recorded("luna-x", "hard-count-f", 273, "01"))
    _write(study / "episode-terra-g-01.json", _recorded("terra-x", "hard-count-g", 754, "01"))
    agg = run_family_study(
        study, pack_dir=PACK_DIR, plan=PLAN, recomputer=RECOMPUTER, family="openai"
    )["aggregate"]
    assert agg["overall"]["errors"] == 0
    assert agg["overall"]["falseRejections"] == 0
