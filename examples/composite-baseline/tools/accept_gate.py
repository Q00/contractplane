#!/usr/bin/env python3
"""Meta-level accept-gate of the HARDENED composite (EXPERIMENTAL).

This is the reviewer's proposed fix: a Rego constraint enforcing the invariant
"an accept transition requires a preceding verification verdict receipt." It
shells out to a REAL `opa eval` of policy/meta_accept.rego over an input built
from the artifact under accept and a verdict receipt:

    input = {"artifact_sha256": <sha of the artifact>,
             "receipt": <the verdict receipt JSON>}

The meta-policy allows the accept only if the receipt carries verdict=="pass"
AND its artifact_sha256 matches the artifact being accepted. Exit 1 (RED) on deny
-- e.g. when no verification ran, so no valid pass receipt exists.

What this gate CANNOT check is the receipt's ORIGIN. It verifies that *a* pass
receipt bound to this artifact exists; it cannot verify that the receipt was
written by the trusted verifier rather than forged by the producer. That
guarantee lives entirely in the workflow wiring (which step the `receipt` input
is sourced from), which nothing in CWL or OPA compels.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def canonical_sha256(artifact: dict) -> str:
    canon = json.dumps(artifact, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: accept_gate.py <artifact.json> <receipt.json> <meta_policy.rego>", file=sys.stderr)
        return 2
    opa = shutil.which("opa")
    if opa is None:
        print("accept-gate ERROR: `opa` binary not found on PATH", file=sys.stderr)
        return 2
    artifact = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    receipt = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    policy = argv[3]
    query_input = json.dumps({"artifact_sha256": canonical_sha256(artifact), "receipt": receipt})
    proc = subprocess.run(
        [opa, "eval", "-d", str(policy), "-I", "data.cp.accept.allow", "--format", "json"],
        input=query_input, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"accept-gate ERROR: opa eval failed: {proc.stderr.strip()}", file=sys.stderr)
        return 2
    allowed = json.loads(proc.stdout)["result"][0]["expressions"][0]["value"] is True
    if not allowed:
        print(
            f"accept-gate DENY: no valid pass receipt for this artifact "
            f"(receipt verdict={receipt.get('verdict')!r})",
            file=sys.stderr,
        )
        return 1
    Path("accepted.json").write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(f"accept-gate ALLOW: pass receipt present, verifier={receipt.get('verifier')!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
