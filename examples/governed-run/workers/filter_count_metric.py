#!/usr/bin/env python3
"""Local-process worker for the ``filter-count`` flow of the governed-run study.

EXPERIMENTAL — dispatched by contractplane.experimental.LocalProcessAdapter.

Reads the caller-owned dataset's numeric ``values`` column and reports how many
values exceed the flow-defined threshold (from the stage binding config, passed
through in the dispatch assignment as ``config.threshold``). The independent
verifier recomputes the same filtered count from the same dataset and the same
threshold, so a truthful count is accepted and any overclaim is rejected.
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
        print("usage: filter_count_metric.py <assignment.json>", file=sys.stderr)
        return 2
    assignment = json.loads(open(argv[1], encoding="utf-8").read())
    dataset = assignment["input"]["dataset"]
    target = assignment["evidenceTargets"]["filter-count-artifact"]
    threshold = assignment.get("config", {}).get("threshold", 0)

    matches = sum(1 for value in _values(dataset) if value > threshold)
    artifact = {"dataset": dataset, "matches": matches, "generatedBy": "filter-count-metric"}

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, sort_keys=True)

    relative = os.path.relpath(target, os.getcwd())
    print(json.dumps({"outputs": {"artifact": relative, "matches": matches}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
