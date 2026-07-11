"""LLM-as-judge verifier baseline for the spontaneous-error study.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

Reviewers call the recomputation-vs-schema-guard differential "definitional": a
structural output guard *cannot*, by construction, catch a schema-valid numeric
error, so its 0/4 on the natural near-misses is a tautology, not a measurement.

An LLM judge is a fairer, non-definitional baseline. It is *not* blind to value
errors by construction — it can, in principle, read the dataset and recount. But
it may also share the producer's tool-less failure mode and wave a near-miss
through. Whether it catches the four natural errors (three of them off-by-one) is
a genuinely open empirical question, and this module scores the answer.

The judge condition mirrors the producer condition exactly: the judge model is
given the producer's claim (the claimed row count), the dataset path, and the
documented counting rule, and must decide ``accept``/``reject`` by **reading the
dataset tool-less** — no code execution. It records its verdict, its own recount
if it makes one, and a rationale. Only a live judge agent records these; this
module never judges anything itself. Unrecorded placeholder slots refuse scoring.

Each judgment is a fixture ``judge-<judgemodel>-on-<producer>-<dataset>.json``
with the shape defined in ``episodes/judge-verdicts/README.md``. The scorer reads
the nine recorded producer claims from the scale2 grid, computes the ground truth
by recomputation, and reports per claim ``{producer, dataset, claimed, truth,
error, judgeVerdict, judgeCorrect, judgeRecount}`` plus a side-by-side of the
judge against the schema guard (0/4) and recomputation (4/4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..compiler import ExecutionPlan
from .episode import EpisodeError, parse_episode
from .natural_study import (
    DATASET_SCALE2_TOKENS,
    HardCountRecomputer,
    _natural_row,
    _rate,
)
from .recompute import Recomputer

JUDGE_COMPARISON_SCHEMA = "contractplane.dev/experimental/llm-judge-comparison/v0"
JUDGE_FIXTURE_SCHEMA = "contractplane.dev/experimental/judge-verdict/v0"
JUDGE_CONDITION = "llm-judge-tool-less"
JUDGE_VERDICTS = ("accept", "reject")
JUDGE_COMPARISON_NOTE = (
    "EXPERIMENTAL LLM-as-judge baseline. A judge model is given the producer's claim, the "
    "dataset path, and the counting rule, and decides accept/reject by reading the dataset "
    "TOOL-LESS (no code), the same condition the producer worked under. Unlike a structural "
    "schema guard (which cannot catch a schema-valid value error by construction), the judge "
    "is not definitionally blind; whether it catches the natural near-misses is measured here, "
    "not assumed. Rows derive from real-recorded judge fixtures only; placeholders skip."
)


class JudgeFixtureError(RuntimeError):
    """A judge-verdict fixture is malformed, a placeholder, or unusable."""


def parse_judge_filename(filename: str) -> tuple[str, str, str]:
    """Split ``judge-<judgemodel>-on-<producer>-<dataset>.json`` into its parts.

    Returns ``(judge_model, producer, scale)`` where ``scale`` is the raw ``f``/
    ``g``/``h`` token. The judge model is whatever precedes ``-on-`` (a ``pending``
    token on unrecorded placeholders); producer and scale follow it.
    """
    stem = filename
    if stem.startswith("judge-"):
        stem = stem[len("judge-"):]
    if stem.endswith(".json"):
        stem = stem[: -len(".json")]
    judge_model, sep, rest = stem.partition("-on-")
    if not sep:
        return stem, "?", "?"
    producer, _, scale = rest.rpartition("-")
    if not producer:
        return judge_model, rest, "?"
    return judge_model, producer, scale


def is_placeholder(raw: dict[str, Any]) -> bool:
    return raw.get("provenance") == "placeholder" or raw.get("status") == "unrecorded"


def validate_judge_fixture(raw: Any, *, source: str = "<memory>") -> dict[str, Any]:
    """Validate a recorded judge-verdict fixture; raise on placeholders/malformed."""
    if not isinstance(raw, dict):
        raise JudgeFixtureError(f"judge fixture {source} must be a JSON object")
    if is_placeholder(raw):
        raise JudgeFixtureError(
            f"judge fixture {source} is an unrecorded placeholder; a live judge must record "
            "a verdict before it can be scored (see episodes/judge-verdicts/README.md)"
        )
    if raw.get("schema") != JUDGE_FIXTURE_SCHEMA:
        raise JudgeFixtureError(
            f"judge fixture {source} has schema {raw.get('schema')!r}, expected {JUDGE_FIXTURE_SCHEMA!r}"
        )
    if raw.get("provenance") != "real-recorded":
        raise JudgeFixtureError(
            f"judge fixture {source} provenance {raw.get('provenance')!r} must be 'real-recorded'"
        )
    verdict = raw.get("verdict")
    if verdict not in JUDGE_VERDICTS:
        raise JudgeFixtureError(
            f"judge fixture {source} verdict {verdict!r} must be one of {list(JUDGE_VERDICTS)}"
        )
    recount = raw.get("judgeRecount")
    if recount is not None and (not isinstance(recount, int) or isinstance(recount, bool)):
        raise JudgeFixtureError(
            f"judge fixture {source} judgeRecount must be an integer or null, got {recount!r}"
        )
    model = raw.get("judgeModel")
    if not isinstance(model, str) or not model:
        raise JudgeFixtureError(f"judge fixture {source} must name a judgeModel")
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise JudgeFixtureError(f"judge fixture {source} must carry a non-empty rationale")
    return raw


def _producer_claims(
    producer_dir: Path,
    *,
    pack_dir: Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    scale_tokens: dict[str, str],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Replay each recorded scale2 base claim; key by ``(producer, scale)``.

    The replay yields the recomputation verdict and schema gate for each claim, so
    the schema-guard and recomputation comparison columns are measured from the
    same episodes the judge sees, not asserted.
    """
    claims: dict[tuple[str, str], dict[str, Any]] = {}
    for scale, dataset in scale_tokens.items():
        for producer in ("opus", "sonnet", "haiku"):
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
                "producerModel": raw.get("model"),
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


def _fraction(caught: int, total: int) -> str:
    return f"{caught}/{total}"


def _verifier_column(rows: list[dict[str, Any]], caught_key: str) -> dict[str, Any]:
    errors = [r for r in rows if r["error"]]
    correct = [r for r in rows if not r["error"]]
    offbyone = [r for r in errors if r["absError"] == 1]
    caught_err = sum(1 for r in errors if r[caught_key])
    caught_obo = sum(1 for r in offbyone if r[caught_key])
    false_rej = sum(1 for r in correct if r[caught_key])
    return {
        "caughtOnErrors": _fraction(caught_err, len(errors)),
        "catchRateOnErrors": _rate(caught_err, len(errors)),
        "caughtOffByOne": _fraction(caught_obo, len(offbyone)),
        "falseRejectionsOnCorrect": _fraction(false_rej, len(correct)),
        "falseRejectionRateOnCorrect": _rate(false_rej, len(correct)),
    }


def _judge_column(rows: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [r for r in rows if r["judged"]]
    errors = [r for r in judged if r["error"]]
    correct = [r for r in judged if not r["error"]]
    offbyone = [r for r in errors if r["absError"] == 1]
    caught_err = sum(1 for r in errors if r["judgeVerdict"] == "reject")
    caught_obo = sum(1 for r in offbyone if r["judgeVerdict"] == "reject")
    false_rej = sum(1 for r in correct if r["judgeVerdict"] == "reject")
    # Recount accuracy: of the judgments where the judge offered its own count,
    # how often did that count equal the recomputed truth? A judge that catches an
    # error but recounts wrong is sharing the producer's tool-less failure mode.
    recounts = [r for r in judged if isinstance(r.get("judgeRecount"), int)]
    recount_ok = sum(1 for r in recounts if r["judgeRecount"] == r["truth"])
    # Denominators are the JUDGED subset, so partial recording is scored honestly
    # (the full grid has 4 errors and 5 correct once every judge slot is recorded).
    return {
        "judged": len(judged),
        "errorsJudged": len(errors),
        "correctJudged": len(correct),
        "caughtOnErrors": _fraction(caught_err, len(errors)),
        "catchRateOnErrors": _rate(caught_err, len(errors)),
        "caughtOffByOne": _fraction(caught_obo, len(offbyone)),
        "falseRejectionsOnCorrect": _fraction(false_rej, len(correct)),
        "falseRejectionRateOnCorrect": _rate(false_rej, len(correct)),
        "recountProvided": len(recounts),
        "recountAccurate": _fraction(recount_ok, len(recounts)),
        "recountAccuracy": _rate(recount_ok, len(recounts)),
    }


def _load_baseline(baseline_path: Path | None) -> dict[str, Any] | None:
    if baseline_path is None or not Path(baseline_path).is_file():
        return None
    try:
        data = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("summary") if isinstance(data, dict) else None


def run_judge_comparison(
    *,
    pack_dir: Path,
    producer_dir: str | Path,
    judge_dir: str | Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    baseline_path: str | Path | None = None,
    scale_tokens: dict[str, str] = DATASET_SCALE2_TOKENS,
) -> dict[str, Any]:
    """Score recorded judge verdicts against ground truth and the other verifiers."""
    producer_dir = Path(producer_dir)
    judge_dir = Path(judge_dir)
    claims = _producer_claims(
        producer_dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer, scale_tokens=scale_tokens
    )

    rows: list[dict[str, Any]] = []
    for path in sorted(judge_dir.glob("judge-*.json")):
        judge_model_fn, producer, scale = parse_judge_filename(path.name)
        claim = claims.get((producer, scale))
        entry: dict[str, Any] = {
            "file": path.name,
            "judgeSlot": judge_model_fn,  # filename judge token (pending/pending2/... or the real id)
            "producer": producer,
            "scale": scale,
            "dataset": scale_tokens.get(scale, scale),
            "judged": False,
        }
        if claim is not None:
            entry.update({
                "claimed": claim["claimed"],
                "truth": claim["truth"],
                "error": claim["error"],
                "absError": claim["absError"],
            })
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["fault"] = f"unreadable judge fixture: {exc}"
            rows.append(entry)
            continue
        if is_placeholder(raw):
            entry["skipped"] = "unrecorded"
            rows.append(entry)
            continue
        if claim is None:
            entry["fault"] = f"no recorded producer claim for {producer!r} on {scale!r}"
            rows.append(entry)
            continue
        try:
            fixture = validate_judge_fixture(raw, source=path.name)
        except JudgeFixtureError as exc:
            entry["fault"] = str(exc)
            rows.append(entry)
            continue
        verdict = fixture["verdict"]
        entry.update({
            "judged": True,
            "judgeModel": fixture["judgeModel"],
            "judgeVerdict": verdict,
            "judgeRecount": fixture.get("judgeRecount"),
            "rationale": fixture.get("rationale"),
            # The judge is CORRECT when it rejects exactly the erroneous claims.
            "judgeCorrect": (verdict == "reject") == claim["error"],
        })
        # A fixture that judged a stale claim is flagged, not silently trusted.
        if fixture.get("claimedRows") is not None and fixture["claimedRows"] != claim["claimed"]:
            entry["claimedRowsMismatch"] = {
                "fixture": fixture["claimedRows"], "producer": claim["claimed"]
            }
        rows.append(entry)

    scored = [r for r in rows if r.get("judged")]
    claim_rows = list(claims.values())
    judge_models = sorted({r["judgeModel"] for r in scored})
    by_judge_model = {m: _judge_column([r for r in scored if r["judgeModel"] == m]) for m in judge_models}
    # Roster of judge tiers by filename slot token, so unrecorded tiers are visible.
    roster: dict[str, dict[str, int]] = {}
    for r in rows:
        slot = roster.setdefault(r["judgeSlot"], {"slots": 0, "recorded": 0})
        slot["slots"] += 1
        if r.get("judged"):
            slot["recorded"] += 1
    comparison = {
        "schemaGuard": _verifier_column(
            [{**c, "caught": c["schema_gate"] == "fail"} for c in claim_rows], "caught"
        ),
        "recomputation": _verifier_column(
            [{**c, "caught": c["recomputation"] == "reject"} for c in claim_rows], "caught"
        ),
        # Pooled across every recorded judge, plus a breakdown per judge model.
        "llmJudge": _judge_column(scored),
        "llmJudgeByModel": by_judge_model,
    }
    return {
        "schema": JUDGE_COMPARISON_SCHEMA,
        "note": JUDGE_COMPARISON_NOTE,
        "condition": JUDGE_CONDITION,
        "producerDir": str(producer_dir),
        "judgeDir": str(judge_dir),
        "producerClaims": len(claim_rows),
        "naturalErrors": sum(1 for c in claim_rows if c["error"]),
        "naturalCorrect": sum(1 for c in claim_rows if not c["error"]),
        "judgeModels": judge_models,
        "judgeRoster": roster,
        "judgments": rows,
        "comparison": comparison,
        "baselineFromGuardrails": _load_baseline(Path(baseline_path) if baseline_path else None),
    }


def write_judge_comparison(report: dict[str, Any], out_path: str | Path) -> Path:
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
    judge_dir_default = pack_dir_default / "episodes" / "judge-verdicts"
    producer_dir_default = pack_dir_default / "episodes" / "study-natural-scale2"
    baseline_default = repo_root / "artifacts" / "guardrails_comparison.json"
    out_default = repo_root / "artifacts" / "llm_judge_comparison.json"

    parser = argparse.ArgumentParser(description="Score the LLM-as-judge verifier baseline.")
    parser.add_argument("--judge-dir", default=str(judge_dir_default))
    parser.add_argument("--producer-dir", default=str(producer_dir_default))
    parser.add_argument("--pack", default=str(pack_dir_default))
    parser.add_argument("--baseline", default=str(baseline_default))
    parser.add_argument("--out", default=str(out_default))
    args = parser.parse_args(argv)

    pack_dir = Path(args.pack)
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="report")
    recomputer = HardCountRecomputer(pack_dir / "datasets")

    report = run_judge_comparison(
        pack_dir=pack_dir,
        producer_dir=args.producer_dir,
        judge_dir=args.judge_dir,
        plan=plan,
        recomputer=recomputer,
        baseline_path=args.baseline,
    )
    target = write_judge_comparison(report, args.out)

    cmp = report["comparison"]
    print(json.dumps(cmp, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\nllm-judge baseline over {report['naturalErrors']} errors / "
        f"{report['naturalCorrect']} correct | schema-guard {cmp['schemaGuard']['caughtOnErrors']}, "
        f"recomputation {cmp['recomputation']['caughtOnErrors']}, judges:"
    )
    for model, col in cmp["llmJudgeByModel"].items():
        print(
            f"  {model}: catch {col['caughtOnErrors']} (offByOne {col['caughtOffByOne']}), "
            f"false-rej {col['falseRejectionsOnCorrect']}, recount-acc {col['recountAccurate']}"
        )
    for slot, prog in report["judgeRoster"].items():
        if prog["recorded"] < prog["slots"]:
            print(f"  [{slot}] {prog['recorded']}/{prog['slots']} recorded (awaiting live judge)")
    print(f"-> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
