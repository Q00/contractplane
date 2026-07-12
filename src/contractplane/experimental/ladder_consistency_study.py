"""Cross-judge consistency-vote verifier over the GPU-ladder judged corpus.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

The sibling :mod:`contractplane.experimental.consistency_study` scores the
cross-judge majority-recount vote on the **nine scale2** producer claims (four of
them natural errors), where it catches only ``1/4`` and abstains on the three
h-band errors whose three judge recounts all disagree. Four scored errors is the
same thin base the ladder judge study widened for the LLM-judge tier.

This module extends the *same* cross-judge consistency verifier to the ladder
judged corpus, so the consistency tier is scored on **16** errors instead of 4.
It derives purely from already-recorded fixtures (the 3-tier x 12-claim ladder
judge grid replayed by :func:`ladder_judge_study.run_ladder_judge_study`); no
fresh sampling and no new recordings.

The vote rule mirrors :func:`consistency_study._cross_judge` exactly: for each of
the 12 ladder claims the three recorded judge recounts vote; if at least two of
the three agree on a number, the verdict is ``reject`` iff the producer's claim
differs from that majority recount, otherwise the vote **ABSTAINS**
(accept-by-default, recorded as such).

Honest design property — the ladder judge grid recorded a *single genuine pass
per dataset per judge tier* (each judge counted ``hard-count-f`` once and
``hard-count-g`` once, reusing that one recount across every slot on that
dataset). So the cross-judge vote on all 11 ``hard-count-f`` ladder claims is
decided by the *same* recount triple (all three judges recounted 273), and the
lone ``hard-count-g`` claim by another single triple. The vote still confronts
each claim's own claimed value, but the recount *agreement* it rests on is shared
within a dataset rather than independently re-derived per claim. This is surfaced
structurally in ``withinDatasetRecountSharing`` and stated in the note, not
hidden.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..compiler import ExecutionPlan
from .consistency_study import _fraction, _majority, _rate
from .ladder_judge_study import LADDER_CLAIM_COUNT, run_ladder_judge_study
from .natural_study import HardCountRecomputer
from .recompute import Recomputer

LADDER_CONSISTENCY_STUDY_SCHEMA = "contractplane.dev/experimental/ladder-consistency-verifier/v0"

LADDER_CONSISTENCY_NOTE = (
    "EXPERIMENTAL cross-judge consistency-vote verifier extended to the GPU-ladder judged "
    "corpus (no fresh sampling). For each of the 12 ladder claims the three recorded judge "
    "recounts vote; if >= 2 of 3 agree on a number the verdict is reject iff the producer's "
    "claim differs from that majority recount, else ABSTAIN (accept-by-default). Mirrors "
    "consistency_study._cross_judge exactly. DESIGN PROPERTY (stated, not hidden): the ladder "
    "judge grid recorded one genuine pass per dataset per judge tier, so within a dataset every "
    "claim's cross-judge vote shares that judge's single recount -- all 11 hard-count-f claims "
    "are decided by the same recount triple (273/273/273) and the one hard-count-g claim by "
    "another. The vote still confronts each claim's own claimed value. Combined with the scale2 "
    "cross-judge tier (1/4, abstain 3) this scores the consistency verifier on 16 errors."
)


def _ladder_cross_judge(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-judge majority-recount vote over ladder judged rows.

    ``judgments`` is the ``judgments`` list produced by
    :func:`ladder_judge_study.run_ladder_judge_study`: one row per recorded judge
    verdict, carrying ``stem``, ``judgeModel``, ``judgeRecount``, ``claimed``,
    ``truth`` and ``error``. Rows are grouped by producer-episode ``stem``; the
    three tier recounts for that claim vote under the same rule as
    :func:`consistency_study._cross_judge`.
    """
    by_stem: dict[str, dict[str, Any]] = {}
    for r in judgments:
        if not r.get("judged"):
            continue
        stem = r["stem"]
        slot = by_stem.setdefault(
            stem,
            {
                "stem": stem,
                "producer": r.get("producer"),
                "dataset": r.get("dataset"),
                "rank": r.get("rank"),
                "claimed": r.get("claimed"),
                "truth": r.get("truth"),
                "error": r.get("error"),
                "recounts": {},
            },
        )
        slot["recounts"][r["judgeModel"]] = r.get("judgeRecount")

    rows: list[dict[str, Any]] = []
    for slot in sorted(by_stem.values(), key=lambda s: (s["rank"] if s["rank"] is not None else 0, s["stem"])):
        recounts = slot["recounts"]
        majority, abstained = _majority(list(recounts.values()))
        verdict = "reject" if (not abstained and majority != slot["claimed"]) else "accept"
        rows.append(
            {
                "stem": slot["stem"],
                "producer": slot["producer"],
                "dataset": slot["dataset"],
                "rank": slot["rank"],
                "claimed": slot["claimed"],
                "truth": slot["truth"],
                "error": slot["error"],
                "judgeRecounts": recounts,
                "majorityRecount": majority,
                "abstained": abstained,
                "verdict": verdict,
                "caught": bool(slot["error"] and verdict == "reject"),
                "falseReject": bool(not slot["error"] and verdict == "reject"),
            }
        )

    errors = [r for r in rows if r["error"]]
    correct = [r for r in rows if not r["error"]]
    caught = sum(1 for r in errors if r["verdict"] == "reject")
    false_rej = sum(1 for r in correct if r["verdict"] == "reject")
    return {
        "description": (
            "Three recorded ladder judge recounts vote per claim; abstain->accept when no two "
            "agree. Reject iff the majority recount disagrees with the producer's claim. Same "
            "rule as the scale2 cross-judge majority-recount verifier."
        ),
        "perClaim": rows,
        "withinDatasetRecountSharing": _within_dataset_recount_sharing(judgments),
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


def _within_dataset_recount_sharing(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose the single-pass-per-dataset design property structurally.

    For each dataset, the distinct recounts each judge tier recorded across all its
    ladder claims. A single genuine pass per dataset means each judge has exactly
    one recount per dataset, so all same-dataset claims share it — the recount
    agreement underlying the vote is shared within a dataset, not independently
    re-derived per claim. ``singlePassPerDataset`` is True when every judge has one
    distinct recount per dataset (the recorded case).
    """
    per_dataset: dict[str, dict[str, set[Any]]] = {}
    claims_per_dataset: dict[str, set[str]] = {}
    for r in judgments:
        if not r.get("judged"):
            continue
        dataset = r.get("dataset")
        per_dataset.setdefault(dataset, {}).setdefault(r["judgeModel"], set()).add(r.get("judgeRecount"))
        claims_per_dataset.setdefault(dataset, set()).add(r["stem"])

    distinct: dict[str, dict[str, list[Any]]] = {}
    single_pass = True
    for dataset, models in per_dataset.items():
        distinct[dataset] = {}
        for model, recounts in sorted(models.items()):
            values = sorted(v for v in recounts if v is not None)
            distinct[dataset][model] = values
            if len(recounts) != 1:
                single_pass = False
    return {
        "distinctRecountsPerJudgePerDataset": {d: distinct[d] for d in sorted(distinct)},
        "claimsPerDataset": {d: len(claims_per_dataset[d]) for d in sorted(claims_per_dataset)},
        "singlePassPerDataset": single_pass,
        "note": (
            "Each judge tier recorded one genuine recount per dataset (single-pass-per-dataset), "
            "so every same-dataset ladder claim's cross-judge vote reuses that one recount. The "
            "vote still confronts each claim's own claimed value; the recount agreement is a "
            "shared within-dataset property, not independent per-claim evidence."
        ),
    }


def _combined_consistency(
    ladder_aggregate: dict[str, Any], *, scale2_consistency: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge the scale2 cross-judge tier with the ladder tier into a 16-error view.

    ``scale2_consistency`` is the report from
    :func:`consistency_study.run_consistency_study`; its ``crossJudgeMajorityRecount``
    aggregate carries the scale2 catch/abstain/false-rejection counts. The ladder
    contributes 12 errors and no correct claims, so the false-rejection evidence
    stays with the scale2 corpus (five correct claims).
    """

    def _num(fraction: str) -> int:
        return int(fraction.split("/")[0])

    lad = ladder_aggregate
    l_errors = lad["errors"]
    l_correct = lad["correct"]
    l_caught = _num(lad["caughtOnErrors"])
    l_false = _num(lad["falseRejectionsOnCorrect"])
    l_abstain = lad["abstainedOnErrors"]

    if scale2_consistency is not None:
        s = scale2_consistency["crossJudgeMajorityRecount"]["aggregate"]
        s_errors = s["errors"]
        s_correct = s["correct"]
        s_caught = _num(s["caughtOnErrors"])
        s_false = _num(s["falseRejectionsOnCorrect"])
        s_abstain = s["abstainedOnErrors"]
    else:
        s_errors = s_correct = s_caught = s_false = s_abstain = 0

    total_errors = s_errors + l_errors
    total_correct = s_correct + l_correct
    total_caught = s_caught + l_caught
    total_false = s_false + l_false
    total_abstain = s_abstain + l_abstain
    return {
        "verifier": "crossJudgeMajorityRecount",
        "scale2": {
            "errors": s_errors,
            "correct": s_correct,
            "caughtOnErrors": _fraction(s_caught, s_errors),
            "catchRateOnErrors": _rate(s_caught, s_errors),
            "abstainedOnErrors": s_abstain,
            "falseRejectionsOnCorrect": _fraction(s_false, s_correct),
        },
        "ladder": {
            "errors": l_errors,
            "correct": l_correct,
            "caughtOnErrors": _fraction(l_caught, l_errors),
            "catchRateOnErrors": _rate(l_caught, l_errors),
            "abstainedOnErrors": l_abstain,
            "falseRejectionsOnCorrect": _fraction(l_false, l_correct),
        },
        "combined": {
            "errors": total_errors,
            "correct": total_correct,
            "caughtOnErrors": _fraction(total_caught, total_errors),
            "catchRateOnErrors": _rate(total_caught, total_errors),
            "abstainedOnErrors": total_abstain,
            "falseRejectionsOnCorrect": _fraction(total_false, total_correct),
        },
        "note": (
            "The cross-judge consistency verifier scored over the union of the scale2 errors and "
            "the ladder errors. Every ladder claim is an error, so its false-rejection denominator "
            "is 0; the false-rejection evidence stays with the scale2 corpus (5 correct claims). "
            "The combined error row pools the catch and abstain counts across both corpora."
        ),
    }


def run_ladder_consistency_study(
    *,
    pack_dir: Path,
    gpu_study_dir: str | Path,
    judge_dir: str | Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    artifact_path: str | Path,
    k: int = LADDER_CLAIM_COUNT,
    scale2_consistency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive and score the cross-judge consistency vote over the ladder corpus.

    Replays the ladder judge grid through :func:`ladder_judge_study.run_ladder_judge_study`
    (which parses only real-recorded judge fixtures and derives truth by replaying each
    producer episode), extracts the three tier recounts per claim, and scores the
    cross-judge majority-recount vote. Given the precomputed ``scale2_consistency`` from
    :func:`consistency_study.run_consistency_study`, reports the combined 16-error table.
    """
    ladder = run_ladder_judge_study(
        pack_dir=pack_dir,
        gpu_study_dir=gpu_study_dir,
        judge_dir=judge_dir,
        plan=plan,
        recomputer=recomputer,
        artifact_path=artifact_path,
        k=k,
    )
    ladder_block = _ladder_cross_judge(ladder["judgments"])
    combined = _combined_consistency(
        ladder_block["aggregate"], scale2_consistency=scale2_consistency
    )
    return {
        "schema": LADDER_CONSISTENCY_STUDY_SCHEMA,
        "note": LADDER_CONSISTENCY_NOTE,
        "gpuStudyDir": str(gpu_study_dir),
        "judgeDir": str(judge_dir),
        "artifactPath": str(artifact_path),
        "ladderErrors": ladder_block["aggregate"]["errors"],
        "ladderCorrect": ladder_block["aggregate"]["correct"],
        "ladderCrossJudgeMajorityRecount": ladder_block,
        "combinedConsistencyTier": combined,
    }


def write_ladder_consistency_study(report: dict[str, Any], out_path: str | Path) -> Path:
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
    from .consistency_study import run_consistency_study

    repo_root = Path(__file__).resolve().parents[3]
    pack_dir_default = repo_root / "examples" / "governed-run"
    gpu_dir_default = pack_dir_default / "episodes" / "study-local-gpu"
    ladder_judge_default = pack_dir_default / "episodes" / "judge-verdicts-ladder"
    scale2_producer_default = pack_dir_default / "episodes" / "study-natural-scale2"
    scale2_judge_default = pack_dir_default / "episodes" / "judge-verdicts"
    artifact_default = repo_root / "artifacts" / "local_gpu_family_study.json"
    out_default = repo_root / "artifacts" / "ladder_consistency.json"

    parser = argparse.ArgumentParser(
        description="Score the cross-judge consistency vote over the GPU-ladder judged corpus."
    )
    parser.add_argument("--gpu-dir", default=str(gpu_dir_default))
    parser.add_argument("--judge-dir", default=str(ladder_judge_default))
    parser.add_argument("--scale2-producer-dir", default=str(scale2_producer_default))
    parser.add_argument("--scale2-judge-dir", default=str(scale2_judge_default))
    parser.add_argument("--artifact", default=str(artifact_default))
    parser.add_argument("--pack", default=str(pack_dir_default))
    parser.add_argument("--out", default=str(out_default))
    args = parser.parse_args(argv)

    pack_dir = Path(args.pack)
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="report")
    recomputer = HardCountRecomputer(pack_dir / "datasets")

    scale2_consistency = run_consistency_study(
        pack_dir=pack_dir,
        producer_dir=args.scale2_producer_dir,
        judge_dir=args.scale2_judge_dir,
        plan=plan,
        recomputer=recomputer,
    )
    report = run_ladder_consistency_study(
        pack_dir=pack_dir,
        gpu_study_dir=args.gpu_dir,
        judge_dir=args.judge_dir,
        plan=plan,
        recomputer=recomputer,
        artifact_path=args.artifact,
        scale2_consistency=scale2_consistency,
    )
    target = write_ladder_consistency_study(report, args.out)

    lad = report["ladderCrossJudgeMajorityRecount"]["aggregate"]
    combined = report["combinedConsistencyTier"]["combined"]
    print(json.dumps(report["combinedConsistencyTier"], ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\nladder cross-judge consistency: catch {lad['caughtOnErrors']} "
        f"(abstained on {lad['abstainedOnErrors']} errors), false-rej {lad['falseRejectionsOnCorrect']}"
    )
    print(
        f"combined consistency tier over {combined['errors']} errors: catch {combined['caughtOnErrors']} "
        f"(abstain {combined['abstainedOnErrors']}), false-rej {combined['falseRejectionsOnCorrect']} -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
