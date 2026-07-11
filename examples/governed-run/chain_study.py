#!/usr/bin/env python3
"""Multi-step agentic claim-chain study runner.

EXPERIMENTAL — replays each recorded 3-step chain episode through the governed
kernel, scoring per-step verdicts and chain-level error-propagation vs
blast-radius containment. Writes artifacts/chain_study.json.

From the repo root:

    .venv/bin/python examples/governed-run/chain_study.py                                   # real slots (skips placeholders)
    .venv/bin/python examples/governed-run/chain_study.py --dir examples/governed-run/episodes/study-chain-smoke
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from contractplane.experimental import run_chain_study, write_chain_study

PACK_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACK_DIR.parents[1]
DEFAULT_STUDY_DIR = PACK_DIR / "episodes" / "study-chain"
DEFAULT_OUT = REPO_ROOT / "artifacts" / "chain_study.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay the agentic chain study.")
    parser.add_argument("--dir", default=str(DEFAULT_STUDY_DIR), help="chain fixture directory")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    args = parser.parse_args(argv)

    report = run_chain_study(args.dir, pack_dir=PACK_DIR, datasets_dir=PACK_DIR / "datasets")
    target = write_chain_study(report, args.out)

    summary = report["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\nchain study: {summary['recorded']} recorded, {summary['skipped']} skipped; "
        f"of {summary['earlyErrorChains']} early-error chains, "
        f"{summary['earlyErrorsPropagatedInClaim']} propagated into the model's final claim and "
        f"{summary['earlyErrorsContainedByGovernance']} were contained by governance -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
