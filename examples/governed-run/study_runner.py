#!/usr/bin/env python3
"""Batch runner for the episode study.

EXPERIMENTAL — replays every recorded producer episode in a directory through the
same governed kernel path and writes an aggregated study table.

From the repo root:

    # the real 3-model x 4-condition grid (skips unrecorded placeholder slots)
    .venv/bin/python examples/governed-run/study_runner.py

    # the synthetic-smoke set (populated rows; NOT citable)
    .venv/bin/python examples/governed-run/study_runner.py --dir examples/governed-run/episodes/study-smoke

By default it writes artifacts/episode_study.json. Placeholder slots are reported
as skipped, never fabricated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    ChainRecomputer,
    FilterCountRecomputer,
    RecordCountRecomputer,
    SumRecomputer,
    run_study,
    write_study,
)
from contractplane.loader import load_domain_pack

PACK_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACK_DIR.parents[1]
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
# One plan per task family the study covers.
PLANS = {
    "report": compile_plan(PACK, entrypoint_id="report"),
    "aggregate": compile_plan(PACK, entrypoint_id="aggregate"),
    "filter-count": compile_plan(PACK, entrypoint_id="filter-count"),
}
# One verifier serving all three families, dispatching by evidence id.
RECOMPUTER = ChainRecomputer(
    [
        RecordCountRecomputer(DATASETS_DIR),
        SumRecomputer(DATASETS_DIR),
        FilterCountRecomputer(DATASETS_DIR),
    ]
)
DEFAULT_STUDY_DIR = PACK_DIR / "episodes" / "study"
DEFAULT_OUT = REPO_ROOT / "artifacts" / "episode_study.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay an episode study and aggregate results.")
    parser.add_argument("--dir", default=str(DEFAULT_STUDY_DIR), help="study fixture directory")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    args = parser.parse_args(argv)

    report = run_study(
        args.dir,
        pack_dir=PACK_DIR,
        plans=PLANS,
        recomputer=RECOMPUTER,
    )
    target = write_study(report, args.out)

    counts = report["aggregate"]["counts"]
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\nstudy: {counts['recorded']} recorded "
        f"({counts['accepted']} accepted, {counts['rejected']} rejected), "
        f"{counts['skipped']} skipped, {counts['error']} error -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
