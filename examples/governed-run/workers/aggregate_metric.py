#!/usr/bin/env python3
"""Local-process worker for the ``aggregate`` flow of the governed-run study.

EXPERIMENTAL — dispatched by contractplane.experimental.LocalProcessAdapter.

Reads the caller-owned dataset's numeric ``values`` column and reports its
honest total. The independent verifier recomputes the same sum from the same
dataset, so a truthful total is accepted and any overclaim is rejected.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"


def _values(dataset: str) -> list:
    source = DATASETS_DIR / f"{dataset}.json"
    if source.is_file():
        return json.loads(source.read_text(encoding="utf-8")).get("values", [])
    return []


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: aggregate_metric.py <assignment.json>", file=sys.stderr)
        return 2
    assignment = json.loads(open(argv[1], encoding="utf-8").read())
    dataset = assignment["input"]["dataset"]
    target = assignment["evidenceTargets"]["aggregate-artifact"]

    total = sum(_values(dataset))
    artifact = {"dataset": dataset, "total": total, "generatedBy": "aggregate-metric"}

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, sort_keys=True)

    relative = os.path.relpath(target, os.getcwd())
    print(json.dumps({"outputs": {"artifact": relative, "total": total}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
