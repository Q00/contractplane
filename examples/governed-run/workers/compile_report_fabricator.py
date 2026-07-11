#!/usr/bin/env python3
"""ADVERSARIAL PROBE worker for the governed-run demo.

EXPERIMENTAL — dispatched by contractplane.experimental.LocalProcessAdapter.

This worker deliberately LIES: whatever the true dataset row count is, it claims
``rows: 100``. The fabricated artifact is still well-shaped, so it passes the
declared evidence schema (``rows`` minimum 1). It exists only to prove that the
independent verifier's *recomputation* — which counts the dataset's records from
the caller-owned source rather than trusting this artifact — catches the lie and
rejects it, so the unit never advances.

It is a governance test probe, not a real capability.
"""

from __future__ import annotations

import json
import os
import sys

FABRICATED_ROWS = 100


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: compile_report_fabricator.py <assignment.json>", file=sys.stderr)
        return 2
    assignment = json.loads(open(argv[1], encoding="utf-8").read())
    dataset = assignment["input"]["dataset"]
    target = assignment["evidenceTargets"]["report-artifact"]

    # The lie: report a fabricated row count regardless of the real data.
    artifact = {"dataset": dataset, "rows": FABRICATED_ROWS, "generatedBy": "compile-report"}

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, sort_keys=True)

    relative = os.path.relpath(target, os.getcwd())
    print(json.dumps({"outputs": {"artifact": relative, "rows": FABRICATED_ROWS}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
