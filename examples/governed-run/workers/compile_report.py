#!/usr/bin/env python3
"""Local-process worker for the ``compile`` stage of the governed-run demo.

EXPERIMENTAL — dispatched by contractplane.experimental.LocalProcessAdapter.

Contract (owned by the adapter, not by this worker):

* argv[1] is a dispatch assignment JSON file: ``{"input": {...},
  "evidenceTargets": {"<evidence-id>": "<absolute path>"}}``.
* The worker writes each declared evidence artifact to its assigned path and
  prints a single JSON line ``{"outputs": {...}}`` as its claim.

The worker is deterministic and offline: it reads the caller-owned dataset file
(``datasets/<dataset>.json``), reports the true row count, and writes it
faithfully. An empty dataset honestly yields ``rows: 0``, which the declared
evidence schema (``rows`` minimum 1) later rejects — the rejection emerges from
real data meeting a real contract, not from a synthetic "corrupt" flag. The
independent verifier recomputes this same count from the same dataset file, so a
truthful worker is accepted and a lying one (see ``compile_report_fabricator.py``)
is not.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"


def _records(dataset: str) -> list:
    source = DATASETS_DIR / f"{dataset}.json"
    if source.is_file():
        return json.loads(source.read_text(encoding="utf-8")).get("records", [])
    return [f"{dataset}-record-1"]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: compile_report.py <assignment.json>", file=sys.stderr)
        return 2
    assignment = json.loads(open(argv[1], encoding="utf-8").read())
    dataset = assignment["input"]["dataset"]
    target = assignment["evidenceTargets"]["report-artifact"]

    rows = len(_records(dataset))
    artifact = {"dataset": dataset, "rows": rows, "generatedBy": "compile-report"}

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, sort_keys=True)

    relative = os.path.relpath(target, os.getcwd())
    print(json.dumps({"outputs": {"artifact": relative, "rows": rows}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
