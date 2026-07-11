#!/usr/bin/env python3
"""Local-process worker for the ``publish`` stage of the governed-run demo.

EXPERIMENTAL — dispatched by contractplane.experimental.LocalProcessAdapter.

In the headline demo this worker is never reached: the ``publish`` stage declares
external side effects and deny-by-default authority refuses it pre-dispatch, so
no subprocess runs. It exists so that a run which is *explicitly* granted
external authority can still be driven end-to-end, proving the denial is a real
authority decision rather than a broken code path.

To stay deterministic and offline it performs no network I/O: it simulates a
distribution endpoint by minting a stable receipt id derived from the artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: publish_report.py <assignment.json>", file=sys.stderr)
        return 2
    assignment = json.loads(open(argv[1], encoding="utf-8").read())
    artifact = assignment["input"]["artifact"]
    target = assignment["evidenceTargets"]["publication-receipt"]

    digest = hashlib.sha256(artifact.encode("utf-8")).hexdigest()[:12]
    receipt = {"receiptId": f"pub-{digest}"}

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, sort_keys=True)

    print(json.dumps({"outputs": {"receiptId": receipt["receiptId"]}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
