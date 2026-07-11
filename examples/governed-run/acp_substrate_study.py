#!/usr/bin/env python3
"""Cross-substrate governed study runner (local-process vs real ACP).

EXPERIMENTAL — runs the governed conditions over BOTH substrates and writes
artifacts/acp_substrate_study.json. The ACP substrate spawns the Node ACP agent
(official @zed-industries SDK) and answers its session/request_permission from
the compiled contract's authority decision.

From the repo root:

    .venv/bin/python examples/governed-run/acp_substrate_study.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from contractplane.experimental import run_substrate_study, write_substrate_study

PACK_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACK_DIR.parents[1]
DEFAULT_OUT = REPO_ROOT / "artifacts" / "acp_substrate_study.json"


def main(argv: list[str] | None = None) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    report = run_substrate_study(
        pack_dir=PACK_DIR,
        datasets_dir=PACK_DIR / "datasets",
        python=sys.executable,
    )
    target = write_substrate_study(report, out)

    print(json.dumps(report["table"], ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nacp available: {report['acpAvailable']} ({report['acpReason']})")
    print(
        f"substrate agreement: {report['agreementCount']}/{report['conditionsCount']} "
        f"conditions identical across substrates -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
