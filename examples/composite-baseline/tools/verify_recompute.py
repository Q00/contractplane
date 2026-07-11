#!/usr/bin/env python3
"""Independent-verification step of the COMPOSITE baseline (EXPERIMENTAL).

The composite analogue of contractplane's RecordCountRecomputer: it recomputes
the row count *from the caller-owned dataset itself* and compares it against the
producer's claimed ``rows``. A schema check alone would only prove the artifact
is well-shaped; recomputation proves it is true, so an overclaim (rows 999 when
the dataset holds 12) or an off-by-one (rows 8 when the dataset holds 7) is
rejected here even though it passed the schema gate.

Exit 0 and copy the artifact forward when the claim matches ground truth; exit 1
(RED pipeline) on any mismatch.

CRITICAL to the comparison: this step is just another line in the CWL workflow.
Nothing in the composite forces it to exist. The misconfigured workflow variant
simply deletes it, and the pipeline still runs green — see ../README.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: verify_recompute.py <artifact.json> <dataset.json>", file=sys.stderr)
        return 2
    artifact = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    dataset = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    ground_truth = len(dataset.get("records", []))
    claimed = artifact.get("rows")
    if claimed != ground_truth:
        print(
            f"verify REJECT: claimed rows={claimed} but recomputed ground truth "
            f"from dataset is {ground_truth}",
            file=sys.stderr,
        )
        return 1
    Path("verified.json").write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(f"verify PASS: claimed rows={claimed} matches recomputed {ground_truth}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
