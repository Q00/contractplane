#!/usr/bin/env python3
"""Provenance-log step of the COMPOSITE baseline (EXPERIMENTAL).

The composite analogue of contractplane's JSONL ledger. It emits a single
PROV-style record (W3C PROV vocabulary: entity / activity / agent, plus
wasGeneratedBy / wasAssociatedWith / used / wasDerivedFrom) describing the run
that reached it. Because this step only runs when every upstream gate passed,
its presence in the log means "this artifact cleared the pipeline" — which is
exactly why a *misconfigured* pipeline that skipped the verify step still writes
a satisfied-looking provenance record for an overclaim.

It writes provenance.json into the working directory (captured as the workflow
output); the driver aggregates these into a single JSONL provenance log outside
the hermetic CWL run, keeping the workflow itself side-effect-free.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: provenance_log.py <token.json> <claim.json> <dataset.json>", file=sys.stderr)
        return 2
    claim = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    dataset = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    record = {
        "prov:entity": {
            "id": f"report-artifact:{claim.get('condition')}",
            "type": "report-artifact",
            "value": claim.get("artifact"),
        },
        "prov:activity": {
            "id": f"composite-run:{claim.get('condition')}",
            "type": "cwl-governed-pipeline",
            "endedAtTime": now,
        },
        "prov:agent": {"id": claim.get("model", "unknown-producer"), "type": "prov:SoftwareAgent"},
        "prov:wasGeneratedBy": f"composite-run:{claim.get('condition')}",
        "prov:wasAssociatedWith": claim.get("model", "unknown-producer"),
        "prov:used": {"dataset": dataset.get("dataset"), "records": len(dataset.get("records", []))},
        "prov:wasDerivedFrom": claim.get("source_fixture"),
    }
    Path("provenance.json").write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(f"provenance: appended PROV record for {claim.get('condition')!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
