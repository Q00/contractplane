#!/usr/bin/env python3
"""Runnable end-to-end demo of the experimental governed execution slice.

EXPERIMENTAL — exercises contractplane.experimental against a real kernel run.

Run the full scenario suite deterministically and offline from the repo root::

    .venv/bin/python examples/governed-run/run_demo.py

Or replay a single recorded producer episode (see episodes/README.md)::

    .venv/bin/python examples/governed-run/run_demo.py --episode examples/governed-run/episodes/episode-synthetic-smoke.json

The scenario suite drives five governed runs, each in a fresh temporary
workspace and ledger:

1. happy path         - compile a valid report; the independent verifier
                        RECOMPUTES the row count from the dataset and accepts.
2. verifier rejection - compile an empty dataset (rows 0); rejected against the
                        declared schema; the unit never advances.
3. fabrication        - a producer overclaims rows=100 when the dataset holds 3;
                        it passes schema but RECOMPUTATION rejects it.
4. authority denial   - external publication with no external grant is refused
                        pre-dispatch by deny-by-default authority.
5. granted authority  - the same publication with an explicit grant succeeds.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.experimental import (
    AuthorityGate,
    AuthorityGrant,
    EpisodeError,
    GovernedRunner,
    RecordCountRecomputer,
    RunResult,
    Workspace,
    load_episode,
    replay_episode,
)
from contractplane.ledger import JsonlLedger
from contractplane.loader import load_domain_pack

PACK_DIR = Path(__file__).resolve().parent
PACK = load_domain_pack(PACK_DIR / "domainpack.yaml")
DATASETS_DIR = PACK_DIR / "datasets"
PLANS = {
    "report": compile_plan(PACK, entrypoint_id="report"),
    "publish": compile_plan(PACK, entrypoint_id="publish"),
    "report-fabricated": compile_plan(PACK, entrypoint_id="report-fabricated"),
}


def _recomputer() -> RecordCountRecomputer:
    return RecordCountRecomputer(DATASETS_DIR)


def _runner(root: Path, plan, *, grant: AuthorityGrant | None = None) -> GovernedRunner:
    return GovernedRunner(
        plan,
        pack_dir=PACK_DIR,
        workspace=Workspace.create(root / "workspace"),
        ledger=JsonlLedger(root / "ledger.jsonl"),
        authority=AuthorityGate(grant),
        recomputer=_recomputer(),
    )


def _show(title: str, report) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))


def _run_scenarios(scratch: Path) -> int:
    happy = _runner(scratch / "a", PLANS["report"]).run(
        {"dataset": "weekly-metrics"}, execution_id="demo-happy"
    )
    _show("1. happy path (recomputed row count matches -> accepted)", happy)
    assert happy.result is RunResult.SUCCEEDED, happy.result
    assert happy.verdicts[-1].method == "recomputation"

    rejected = _runner(scratch / "b", PLANS["report"]).run(
        {"dataset": "empty-dataset"}, execution_id="demo-rejected"
    )
    _show("2. verifier rejection (rows=0 violates evidence schema)", rejected)
    assert rejected.result is RunResult.REJECTED, rejected.result

    fabricated = _runner(scratch / "c", PLANS["report-fabricated"]).run(
        {"dataset": "weekly-metrics"}, execution_id="demo-fabricated"
    )
    _show("3. fabrication (claims rows=100, ground truth 3 -> recomputation rejects)", fabricated)
    assert fabricated.result is RunResult.REJECTED, fabricated.result
    assert fabricated.verdicts[-1].method == "recomputation"
    assert "recomputed ground truth" in fabricated.verdicts[-1].reason

    denied = _runner(scratch / "d", PLANS["publish"]).run(
        {"artifact": "evidence/compile.report-artifact.json"}, execution_id="demo-denied"
    )
    _show("4. authority denial (external side effect, no grant)", denied)
    assert denied.result is RunResult.DENIED, denied.result

    granted = _runner(
        scratch / "e", PLANS["publish"], grant=AuthorityGrant(allow_external=True)
    ).run({"artifact": "evidence/compile.report-artifact.json"}, execution_id="demo-granted")
    _show("5. granted authority (explicit external grant)", granted)
    assert granted.result is RunResult.SUCCEEDED, granted.result

    print("\nAll five governed runs behaved as governed. OK")
    return 0


def _run_episode(scratch: Path, episode_path: str) -> int:
    try:
        episode = load_episode(episode_path)
    except EpisodeError as exc:
        print(f"cannot replay episode: {exc}")
        return 2
    plan = PLANS.get(episode.flow)
    if plan is None:
        print(f"episode names unknown flow {episode.flow!r}; known: {sorted(PLANS)}")
        return 2
    report = replay_episode(
        episode,
        plan=plan,
        pack_dir=PACK_DIR,
        workspace=Workspace.create(scratch / "workspace"),
        ledger=JsonlLedger(scratch / "ledger.jsonl"),
        execution_id="episode-replay",
        recomputer=_recomputer(),
    )
    label = f"episode replay (provenance={episode.provenance}, adversarial={episode.adversarial})"
    _show(label, report)
    if not episode.citable:
        print("NOTE: this episode is a synthetic-smoke fixture and must NOT be cited.")
    print(f"\nreplayed episode -> {report.result.value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Governed-run experimental demo.")
    parser.add_argument(
        "--episode", help="path to a recorded producer episode JSON to replay"
    )
    args = parser.parse_args(argv)

    scratch = Path(tempfile.mkdtemp(prefix="governed-run-"))
    try:
        if args.episode:
            return _run_episode(scratch, args.episode)
        return _run_scenarios(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
