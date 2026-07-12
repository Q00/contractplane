#!/usr/bin/env python3
"""Replay a multi-model family harvest through the governed path (EXPERIMENTAL).

Shared runner for the parallel Track A (OpenAI luna/terra/sol grid, fixtures in
``episodes/study-openai/``) and Track B (GPU local-model ladder, fixtures in
``episodes/study-local-gpu/``). Replays every recorded episode through the SAME
recomputation-governed kernel path as the frontier grids, then aggregates overall,
per dataset, per model, and per model x dataset (Wilson 95% CIs, error-magnitude
distributions, parse-failure routing) plus a family-aware capability-frontier
comparison against the recorded Anthropic-tier rates.

From the repo root:

    .venv/bin/python examples/governed-run/family_study_runner.py \
        --dir examples/governed-run/episodes/study-openai \
        --family openai --out artifacts/openai_family_study.json

Deterministic and offline: it only replays already-recorded fixtures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    HardCountRecomputer,
    run_family_study,
    write_natural_study,
)
from contractplane.loader import load_domain_pack

PACK_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACK_DIR.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay a multi-model family harvest and aggregate results."
    )
    parser.add_argument("--dir", required=True, help="study fixture directory")
    parser.add_argument("--family", required=True, help="family label (e.g. openai, local-gpu)")
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument("--pack", default=str(PACK_DIR), help="domain pack directory")
    args = parser.parse_args(argv)

    pack_dir = Path(args.pack)
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="report")
    recomputer = HardCountRecomputer(pack_dir / "datasets")

    report = run_family_study(
        args.dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer, family=args.family
    )
    target = write_natural_study(report, args.out)

    overall = report["aggregate"]["overall"]
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\n{args.family} family study: N={overall['recorded']} recorded "
        f"({overall['errors']} natural errors, {overall['caught']} caught, "
        f"{overall['missed']} missed, {overall['falseRejections']} false-rejections, "
        f"{overall['parseFailures']} parse-failures) -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
