#!/usr/bin/env python3
"""Producer self-attestation forger (EXPERIMENTAL) — the drift-on-the-guard probe.

Models the realistic second-order drift where an integrator, having dropped the
expensive recompute step, wires the hardened accept-gate to read its verdict
receipt from a producer-side source (an "attestation the tool emits about itself"
— an extremely common pattern) instead of from the independent verifier.

This tool stands in for that producer: it takes the producer's own artifact and
emits a verdict receipt claiming verdict=="pass" with the CORRECT artifact hash,
without any recomputation. Because the meta-policy can only check that a pass
receipt bound to this artifact exists — not who wrote it — the forged receipt
satisfies the accept-gate and an overclaim sails through green.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def canonical_sha256(artifact: dict) -> str:
    canon = json.dumps(artifact, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: forge_receipt.py <artifact.json>", file=sys.stderr)
        return 2
    artifact = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    receipt = {
        "verdict": "pass",
        "verifier": "compile-report-SELF-ATTESTED",
        "method": "none-forged",
        "artifact_sha256": canonical_sha256(artifact),
        "forged": True,
    }
    Path("verdict-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print("forge: producer self-attested a pass receipt (no recomputation performed)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
