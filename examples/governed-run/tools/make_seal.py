#!/usr/bin/env python3
"""Create a commit-reveal seal over the hard-dataset ground truths (EXPERIMENTAL).

Computes authoritative truths (record counts via HardCountRecomputer.count_records,
value sums via HardSumRecomputer.sum_records) for the datasets in scope, draws a
random salt, and writes:

* ``seals/seal-<tag>.json``          — COMMIT this (hash + metadata, no truths)
* ``seals/PREIMAGE-seal-<tag>.local.json`` — DO NOT COMMIT until reveal
  (gitignored by ``seals/.gitignore``)

Run BEFORE any Track A/B recording starts:

    .venv/bin/python examples/governed-run/tools/make_seal.py --tag 2026-07-12-trackAB

Verify (at reveal, or any time locally):

    .venv/bin/python -m contractplane.experimental.sealing \
        examples/governed-run/seals/seal-<tag>.json \
        examples/governed-run/seals/PREIMAGE-seal-<tag>.local.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from contractplane.experimental import HardCountRecomputer, build_seal
from contractplane.experimental.natural_study import HardSumRecomputer

PACK_DIR = Path(__file__).resolve().parents[1]
DATASETS_DIR = PACK_DIR / "datasets"
SEALS_DIR = PACK_DIR / "seals"

DATASETS = (
    "hard-count-f",
    "hard-count-g",
    "hard-count-g2",
    "hard-count-g3",
    "hard-count-h",
    "hard-count-h2",
    "hard-count-h3",
)


def compute_truths() -> dict[str, int]:
    counter = HardCountRecomputer(DATASETS_DIR)
    summer = HardSumRecomputer(DATASETS_DIR)
    truths: dict[str, int] = {}
    for name in DATASETS:
        data = json.loads((DATASETS_DIR / f"{name}.json").read_text(encoding="utf-8"))
        count = counter.count_records(data)
        total = summer.sum_records(data)
        if count is None or total is None:
            raise SystemExit(f"could not recompute truths for {name}")
        truths[f"{name}:count"] = count
        truths[f"{name}:sum"] = total
    return truths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal hard-dataset truths (commit-reveal).")
    parser.add_argument("--tag", required=True, help="seal tag, e.g. 2026-07-12-trackAB")
    args = parser.parse_args(argv)

    seal_path = SEALS_DIR / f"seal-{args.tag}.json"
    preimage_path = SEALS_DIR / f"PREIMAGE-seal-{args.tag}.local.json"
    if seal_path.exists():
        raise SystemExit(f"refusing to overwrite existing seal {seal_path}")

    truths = compute_truths()
    seal, preimage = build_seal(
        truths,
        sealed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        scope=(
            "Ground truths (record counts and value sums) for the hard-count datasets "
            "used by the parallel harvest tracks (Track A: OpenAI family; Track B: GPU "
            "local ladder). Sealed before any recording in either track."
        ),
    )
    SEALS_DIR.mkdir(exist_ok=True)
    seal_path.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    preimage_path.write_text(json.dumps(preimage, indent=2) + "\n", encoding="utf-8")
    print(f"seal      -> {seal_path}  (commit this)")
    print(f"preimage  -> {preimage_path}  (LOCAL ONLY until reveal)")
    print(f"commitment: {seal['commitment']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
