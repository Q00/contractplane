#!/usr/bin/env python3
"""Replay the large-N local-model harvest through the governed path (EXPERIMENTAL).

Replays every episode in ``episodes/study-local/`` through the SAME recomputation-governed
kernel path the frontier natural grids use (dispatch -> claim -> recompute-verify ->
verdict) and writes an aggregated study table to ``artifacts/local_model_study.json``:
per-episode rows plus, per dataset and overall, the natural error rate (with a Wilson 95%
CI), the error-magnitude distribution, the governed path's catch rate on natural errors,
the false-rejection rate on correct claims, and the parse-failure count -- and a
capability-frontier comparison against the recorded frontier per-model rates.

From the repo root:

    .venv/bin/python examples/governed-run/local_study_runner.py

Deterministic and offline: it only replays already-recorded fixtures (no ollama needed).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    HardCountRecomputer,
    run_local_study,
    write_natural_study,
)
from contractplane.loader import load_domain_pack

PACK_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACK_DIR.parents[1]
DEFAULT_STUDY_DIR = PACK_DIR / "episodes" / "study-local"
DEFAULT_OUT = REPO_ROOT / "artifacts" / "local_model_study.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay the local-model harvest and aggregate results.")
    parser.add_argument("--dir", default=str(DEFAULT_STUDY_DIR), help="study fixture directory")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    parser.add_argument("--pack", default=str(PACK_DIR), help="domain pack directory")
    args = parser.parse_args(argv)

    pack_dir = Path(args.pack)
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="report")
    recomputer = HardCountRecomputer(pack_dir / "datasets")

    report = run_local_study(args.dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer)
    target = write_natural_study(report, args.out)

    overall = report["aggregate"]["overall"]
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\nlocal-model study: N={overall['recorded']} recorded "
        f"({overall['errors']} natural errors, {overall['caught']} caught, "
        f"{overall['missed']} missed, {overall['falseRejections']} false-rejections, "
        f"{overall['parseFailures']} parse-failures) -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
