#!/usr/bin/env python3
"""Policy-gate step of the COMPOSITE baseline (EXPERIMENTAL).

The composite analogue of contractplane's deny-by-default AuthorityGate. It
shells out to a REAL OPA binary (`opa eval`) evaluating a Rego policy over an
effect descriptor {sideEffects, grant}. Local side effects are allowed; an
external side effect is allowed only with an explicit external grant. Exit 0 and
copy the token forward when allowed; exit 1 (RED pipeline) when denied.

If the `opa` binary is not on PATH this tool exits 2 and says so, rather than
silently substituting a fake — a missing tool must never look like a pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: policy_gate.py <token.json> <effect.json> <policy.rego>", file=sys.stderr)
        return 2
    opa = shutil.which("opa")
    if opa is None:
        print("policy-gate ERROR: `opa` binary not found on PATH", file=sys.stderr)
        return 2
    policy = argv[3]
    effect_text = Path(argv[2]).read_text(encoding="utf-8")
    proc = subprocess.run(
        [opa, "eval", "-d", str(policy), "-I", "data.cp.authz.allow", "--format", "json"],
        input=effect_text,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"policy-gate ERROR: opa eval failed: {proc.stderr.strip()}", file=sys.stderr)
        return 2
    result = json.loads(proc.stdout)
    allowed = result["result"][0]["expressions"][0]["value"] is True
    effect = json.loads(effect_text)
    if not allowed:
        print(
            f"policy-gate DENY: effect {effect.get('sideEffects')!r} not authorized "
            f"(grant={effect.get('grant')})",
            file=sys.stderr,
        )
        return 1
    Path("authorized.json").write_text(effect_text, encoding="utf-8")
    print(f"policy-gate ALLOW: effect {effect.get('sideEffects')!r} authorized", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
