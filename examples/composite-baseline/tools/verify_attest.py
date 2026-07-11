#!/usr/bin/env python3
"""Attesting independent-verification step of the HARDENED composite (EXPERIMENTAL).

Like verify_recompute.py, it recomputes the row count from the caller-owned
dataset and rejects (exit 1) a claim that does not match. In ADDITION it emits a
*verdict receipt* (verdict-receipt.json) binding a PASS verdict to the sha256 of
the exact artifact it checked. The hardened accept-gate's meta-policy consults
this receipt so that an accept transition requires a preceding verify verdict.

The receipt binds the verdict to the artifact hash, so it cannot be replayed for
a different artifact. It does NOT and cannot attest its own provenance: OPA sees
a JSON document, not the identity of the step that wrote it. Whether the receipt
is trustworthy therefore depends entirely on WHERE the accept-gate is wired to
read it from — see forge_receipt.py for the drift that exploits this.
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
    if len(argv) != 3:
        print("usage: verify_attest.py <artifact.json> <dataset.json>", file=sys.stderr)
        return 2
    artifact = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    dataset = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    ground_truth = len(dataset.get("records", []))
    claimed = artifact.get("rows")
    if claimed != ground_truth:
        print(
            f"verify REJECT: claimed rows={claimed} but recomputed ground truth is {ground_truth}",
            file=sys.stderr,
        )
        return 1
    Path("verified.json").write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    receipt = {
        "verdict": "pass",
        "verifier": "recompute",
        "method": "recomputation",
        "artifact_sha256": canonical_sha256(artifact),
        "recomputed": ground_truth,
    }
    Path("verdict-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(f"verify PASS: rows={claimed} matches {ground_truth}; emitted verdict receipt", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
