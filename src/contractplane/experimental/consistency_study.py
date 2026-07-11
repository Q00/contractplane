"""Consistency-vote verifier baselines, derived from already-recorded data.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

Reviewers noted the hierarchy never includes a sampling / self-consistency
verifier. This module derives and scores two such verifiers **from data already
recorded** (no fresh sampling), each precisely labelled:

(a) **Cross-judge majority-recount** — for each of the nine scale2 producer claims,
    the three recorded judge recounts (opus/sonnet/haiku judges) vote. The majority
    recount is the value at least two judges agree on; with no majority the verifier
    ABSTAINS (accept-by-default, recorded as such). Verdict = reject iff the majority
    recount disagrees with the producer's claim.

(b) **Same-model attempt-consistency** — where producer repetitions exist (r1/r2/r3
    at g and h), the three own attempts of one model vote. Verdict = flag the first
    attempt (r1) iff the majority of the model's own attempts disagrees with r1. This
    is derived from the recorded producer repetitions, **not** fresh k-sampling of a
    verifier, and is labelled so.

Neither verifier is a substitute for recomputation; the point is to measure, not
assume, how a consistency vote fares on natural near-misses. Results are written to
``artifacts/consistency_verifier.json`` side-by-side with the existing tiers
(schema guard 0/4, single judges, recomputation 4/4).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..compiler import ExecutionPlan
from .episode import EpisodeError, parse_episode
from .judge_study import is_placeholder, parse_judge_filename, validate_judge_fixture
from .natural_study import DATASET_SCALE2_TOKENS, HardCountRecomputer, _natural_row
from .recompute import Recomputer

CONSISTENCY_STUDY_SCHEMA = "contractplane.dev/experimental/consistency-verifier/v0"
PRODUCERS: tuple[str, ...] = ("opus", "sonnet", "haiku")
REPETITION_SCALES: tuple[str, ...] = ("g", "h")
CONSISTENCY_NOTE = (
    "EXPERIMENTAL consistency-vote verifiers derived from ALREADY-RECORDED data (no fresh "
    "sampling). Cross-judge majority-recount votes the three recorded judge recounts per claim "
    "(abstains -> accept when they disagree). Same-model attempt-consistency votes a producer's "
    "own recorded r1/r2/r3 repetitions -- derived from repetitions, NOT fresh k-sampling. Both "
    "are scored beside schema guard (0/4), single judges, and recomputation (4/4)."
)


def _majority(values: list[Any]) -> tuple[Any | None, bool]:
    """Return ``(majority_value, abstained)``; abstain when no value has >= 2 votes."""
    present = [v for v in values if v is not None]
    if not present:
        return None, True
    value, count = Counter(present).most_common(1)[0]
    if count >= 2:
        return value, False
    return None, True


def _fraction(caught: int, total: int) -> str:
    return f"{caught}/{total}"


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


def _load_producer_claims(
    producer_dir: Path,
    *,
    pack_dir: Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    scale_tokens: dict[str, str],
) -> dict[tuple[str, str], dict[str, Any]]:
    claims: dict[tuple[str, str], dict[str, Any]] = {}
    for scale, dataset in scale_tokens.items():
        for producer in PRODUCERS:
            path = producer_dir / f"episode-{producer}-{scale}.json"
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            if is_placeholder(raw):
                continue
            try:
                episode = parse_episode(raw, source=path.name)
                row = _natural_row(episode, plan=plan, pack_dir=pack_dir, recomputer=recomputer)
            except EpisodeError:
                continue
            claims[(producer, scale)] = {
                "producer": producer,
                "scale": scale,
                "dataset": dataset,
                "claimed": row["claimed"],
                "truth": row["truth"],
                "error": row["error"],
                "absError": row["absoluteError"],
                "schema_gate": row["schema_gate"],
                "recomputation": "reject" if row["verdict"] == "rejected" else "accept",
            }
    return claims


def _judge_verdicts(judge_dir: Path, producer: str, scale: str) -> dict[str, dict[str, Any]]:
    """Recorded ``{judgeModel: {verdict, recount}}`` for one producer claim."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(judge_dir.glob(f"judge-*-on-{producer}-{scale}.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if is_placeholder(raw):
            continue
        _, fn_producer, fn_scale = parse_judge_filename(path.name)
        if (fn_producer, fn_scale) != (producer, scale):
            continue
        fixture = validate_judge_fixture(raw, source=path.name)
        out[fixture["judgeModel"]] = {
            "verdict": fixture["verdict"],
            "recount": fixture.get("judgeRecount"),
        }
    return out


def _cross_judge(
    claims: dict[tuple[str, str], dict[str, Any]], judge_dir: Path
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for (producer, scale), claim in sorted(claims.items()):
        verdicts = _judge_verdicts(judge_dir, producer, scale)
        recounts = {model: v["recount"] for model, v in verdicts.items()}
        majority, abstained = _majority(list(recounts.values()))
        verdict = "reject" if (not abstained and majority != claim["claimed"]) else "accept"
        rows.append({
            "producer": producer,
            "dataset": claim["dataset"],
            "claimed": claim["claimed"],
            "truth": claim["truth"],
            "error": claim["error"],
            "judgeRecounts": recounts,
            "majorityRecount": majority,
            "abstained": abstained,
            "verdict": verdict,
            "caught": bool(claim["error"] and verdict == "reject"),
            "falseReject": bool(not claim["error"] and verdict == "reject"),
        })
    errors = [r for r in rows if r["error"]]
    correct = [r for r in rows if not r["error"]]
    caught = sum(1 for r in errors if r["verdict"] == "reject")
    false_rej = sum(1 for r in correct if r["verdict"] == "reject")
    return {
        "description": (
            "Three recorded judge recounts vote per claim; abstain->accept when no two agree. "
            "Reject iff the majority recount disagrees with the producer's claim."
        ),
        "perClaim": rows,
        "aggregate": {
            "errors": len(errors),
            "correct": len(correct),
            "caughtOnErrors": _fraction(caught, len(errors)),
            "catchRateOnErrors": _rate(caught, len(errors)),
            "falseRejectionsOnCorrect": _fraction(false_rej, len(correct)),
            "falseRejectionRateOnCorrect": _rate(false_rej, len(correct)),
            "abstentions": sum(1 for r in rows if r["abstained"]),
            "abstainedOnErrors": sum(1 for r in errors if r["abstained"]),
        },
    }


def _attempt_consistency(
    producer_dir: Path,
    *,
    pack_dir: Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    scale_tokens: dict[str, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for scale in REPETITION_SCALES:
        dataset = scale_tokens.get(scale, scale)
        truth = None
        expected = recomputer.recompute(plan.stages[0], "report-artifact", {"dataset": dataset})
        if expected:
            truth = expected.get("rows")
        for producer in PRODUCERS:
            filenames = [
                f"episode-{producer}-{scale}.json",
                f"episode-{producer}-{scale}-r2.json",
                f"episode-{producer}-{scale}-r3.json",
            ]
            attempts: list[int | None] = []
            for name in filenames:
                path = producer_dir / name
                if not path.is_file():
                    attempts.append(None)
                    continue
                raw = json.loads(path.read_text(encoding="utf-8"))
                if is_placeholder(raw):
                    attempts.append(None)
                    continue
                artifact = raw.get("claim", {}).get("artifact", {}).get("report-artifact", {})
                attempts.append(artifact.get("rows"))
            if len([a for a in attempts if a is not None]) < 2 or attempts[0] is None or truth is None:
                continue
            r1 = attempts[0]
            majority, abstained = _majority(attempts)
            flagged = bool(not abstained and majority != r1)
            r1_error = r1 != truth
            rows.append({
                "model": producer,
                "dataset": dataset,
                "truth": truth,
                "attempts": attempts,
                "r1Claim": r1,
                "r1Error": r1_error,
                "majorityOfOwnAttempts": majority,
                "abstained": abstained,
                "flaggedR1": flagged,
                "correctlyFlaggedError": bool(r1_error and flagged),
                "falseFlagOnCorrect": bool(not r1_error and flagged),
            })
    erroneous = [r for r in rows if r["r1Error"]]
    correct = [r for r in rows if not r["r1Error"]]
    flagged_err = sum(1 for r in erroneous if r["flaggedR1"])
    false_flags = sum(1 for r in correct if r["flaggedR1"])
    return {
        "description": (
            "A producer's own recorded r1/r2/r3 attempts vote; flag r1 iff the majority of its "
            "own attempts disagrees with r1. DERIVED FROM PRODUCER REPETITIONS, not fresh "
            "k-sampling of a verifier."
        ),
        "scope": "model x dataset with 3 recorded attempts (g and h only)",
        "perGroup": rows,
        "aggregate": {
            "erroneousFirstAttempts": len(erroneous),
            "flaggedErroneousFirstAttempts": _fraction(flagged_err, len(erroneous)),
            "flagRateOnErroneousFirst": _rate(flagged_err, len(erroneous)),
            "correctFirstAttempts": len(correct),
            "falseFlagsOnCorrectFirst": _fraction(false_flags, len(correct)),
            "falseFlagRateOnCorrectFirst": _rate(false_flags, len(correct)),
        },
    }


def _single_judge_columns(
    claims: dict[tuple[str, str], dict[str, Any]], judge_dir: Path
) -> dict[str, dict[str, Any]]:
    """Per single-judge catch/false-rejection from recorded judge VERDICTS."""
    per_model: dict[str, dict[str, int]] = {}
    for (producer, scale), claim in claims.items():
        for model, v in _judge_verdicts(judge_dir, producer, scale).items():
            slot = per_model.setdefault(model, {"caught": 0, "errors": 0, "false": 0, "correct": 0})
            if claim["error"]:
                slot["errors"] += 1
                if v["verdict"] == "reject":
                    slot["caught"] += 1
            else:
                slot["correct"] += 1
                if v["verdict"] == "reject":
                    slot["false"] += 1
    return {
        model: {
            "caughtOnErrors": _fraction(s["caught"], s["errors"]),
            "catchRateOnErrors": _rate(s["caught"], s["errors"]),
            "falseRejectionsOnCorrect": _fraction(s["false"], s["correct"]),
        }
        for model, s in sorted(per_model.items())
    }


def run_consistency_study(
    *,
    pack_dir: Path,
    producer_dir: str | Path,
    judge_dir: str | Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    scale_tokens: dict[str, str] = DATASET_SCALE2_TOKENS,
) -> dict[str, Any]:
    """Derive and score the two consistency-vote verifiers from recorded data."""
    producer_dir = Path(producer_dir)
    judge_dir = Path(judge_dir)
    claims = _load_producer_claims(
        producer_dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer, scale_tokens=scale_tokens
    )
    cross_judge = _cross_judge(claims, judge_dir)
    attempt = _attempt_consistency(
        producer_dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer, scale_tokens=scale_tokens
    )

    claim_rows = list(claims.values())
    errors = [c for c in claim_rows if c["error"]]
    correct = [c for c in claim_rows if not c["error"]]

    def _column(caught_pred, false_pred) -> dict[str, Any]:
        caught = sum(1 for c in errors if caught_pred(c))
        false_rej = sum(1 for c in correct if false_pred(c))
        return {
            "caughtOnErrors": _fraction(caught, len(errors)),
            "falseRejectionsOnCorrect": _fraction(false_rej, len(correct)),
        }

    verifiers = {
        "schemaGuard": _column(lambda c: c["schema_gate"] == "fail", lambda c: c["schema_gate"] == "fail"),
        "recomputation": _column(lambda c: c["recomputation"] == "reject", lambda c: c["recomputation"] == "reject"),
        "crossJudgeMajorityRecount": {
            "caughtOnErrors": cross_judge["aggregate"]["caughtOnErrors"],
            "falseRejectionsOnCorrect": cross_judge["aggregate"]["falseRejectionsOnCorrect"],
        },
    }
    for model, col in _single_judge_columns(claims, judge_dir).items():
        verifiers[f"singleJudge/{model}"] = {
            "caughtOnErrors": col["caughtOnErrors"],
            "falseRejectionsOnCorrect": col["falseRejectionsOnCorrect"],
        }

    return {
        "schema": CONSISTENCY_STUDY_SCHEMA,
        "note": CONSISTENCY_NOTE,
        "producerDir": str(producer_dir),
        "judgeDir": str(judge_dir),
        "producerClaims": len(claim_rows),
        "naturalErrors": len(errors),
        "naturalCorrect": len(correct),
        "crossJudgeMajorityRecount": cross_judge,
        "sameModelAttemptConsistency": attempt,
        "comparison": {
            "scope": f"{len(claim_rows)} scale2 natural claims ({len(errors)} errors, {len(correct)} correct)",
            "verifiers": verifiers,
        },
    }


def write_consistency_study(report: dict[str, Any], out_path: str | Path) -> Path:
    target = Path(out_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    import argparse

    from ..compiler import compile_plan
    from ..loader import load_domain_pack

    repo_root = Path(__file__).resolve().parents[3]
    pack_dir_default = repo_root / "examples" / "governed-run"
    producer_dir_default = pack_dir_default / "episodes" / "study-natural-scale2"
    judge_dir_default = pack_dir_default / "episodes" / "judge-verdicts"
    out_default = repo_root / "artifacts" / "consistency_verifier.json"

    parser = argparse.ArgumentParser(description="Score consistency-vote verifier baselines.")
    parser.add_argument("--producer-dir", default=str(producer_dir_default))
    parser.add_argument("--judge-dir", default=str(judge_dir_default))
    parser.add_argument("--pack", default=str(pack_dir_default))
    parser.add_argument("--out", default=str(out_default))
    args = parser.parse_args(argv)

    pack_dir = Path(args.pack)
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="report")
    recomputer = HardCountRecomputer(pack_dir / "datasets")

    report = run_consistency_study(
        pack_dir=pack_dir, producer_dir=args.producer_dir, judge_dir=args.judge_dir,
        plan=plan, recomputer=recomputer,
    )
    target = write_consistency_study(report, args.out)

    cj = report["crossJudgeMajorityRecount"]["aggregate"]
    ac = report["sameModelAttemptConsistency"]["aggregate"]
    print(json.dumps(report["comparison"], ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\ncross-judge majority-recount: catch {cj['caughtOnErrors']} "
        f"(abstained on {cj['abstainedOnErrors']} errors), false-rej {cj['falseRejectionsOnCorrect']}"
    )
    print(
        f"same-model attempt-consistency (from repetitions): flags {ac['flaggedErroneousFirstAttempts']} "
        f"erroneous first attempts BUT {ac['falseFlagsOnCorrectFirst']} false flags on correct ones -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
