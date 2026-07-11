#!/usr/bin/env python3
"""Producer step of the COMPOSITE baseline (EXPERIMENTAL).

This is the CWL-orchestrated analogue of the contractplane local-process
producer. To keep the two sides strictly comparable it does NOT re-run a live
model: it replays a *recorded* producer claim (the same recorded-episode replay
path the contractplane study uses) and emits the artifact the model claimed.

Input : a claim file (see ../claims/*.claim.json), itself carrying the
        ``artifact`` object lifted verbatim from a recorded sonnet episode
        fixture under examples/governed-run/episodes/study/.
Output : ``artifact.json`` — the producer's claimed report artifact, exactly as
         a real producer would drop it into the run workspace.

The producer is deliberately trust-preserving: it forwards whatever the model
claimed (including an overclaim or a schema-violating artifact). Catching a bad
claim is the job of the *downstream* gates, never the producer — which is the
whole point of the comparison.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: run_producer.py <claim.json>", file=sys.stderr)
        return 2
    claim = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    artifact = claim["artifact"]
    Path("artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(
        f"producer: replayed recorded claim for condition "
        f"{claim.get('condition')!r} -> artifact.json",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
