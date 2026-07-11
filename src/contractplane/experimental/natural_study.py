"""Spontaneous-error ("natural") study runner and aggregation.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

The sibling :mod:`contractplane.experimental.study` grid uses **instructed**
adversarial probes: the task literally tells the model to overclaim or claim an
off-by-one count. A reviewer can fairly call that "definitional rather than
measured" — of course the governed path rejects an error we asked the model to
make.

This module measures the harder question. It replays episodes recorded under a
**natural** condition: the recorder genuinely attempts a hard counting task,
tool-less (by inspection, no code execution), and reports its honest best answer.
Any error is *spontaneous*, not instructed. The runner then measures whether the
recomputation-based governed path catches those natural errors.

The task is deliberately error-prone for a model reading the raw data without
executing code — records split across nested groups, near-duplicate ids, and a
few metadata entries shaped like records — but it is completely **fair**: the
counting rule is stated precisely (see the study README and each episode's
``task``) so there is one unambiguous ground truth. :class:`HardCountRecomputer`
implements exactly that rule mechanically, so the verifier's ground truth is
derived from the caller-owned dataset, never from the recorder's claim.

Honesty protocol (mirrors :mod:`study`):

* Only ``real-recorded`` episodes are evidence. Unrecorded placeholder slots are
  reported ``skipped: "unrecorded"`` and never fabricated.
* The recorder must NOT check itself with code before or after; whatever it
  claims is recorded verbatim. The recorder is never told the true count.
* ``synthetic-smoke`` fixtures are wiring aids and are flagged non-citable by the
  episode layer.

Per-episode row: ``{model, dataset, attempt, claimed, truth, error, verdict,
caught}`` where ``error = (claimed != truth)`` and ``caught = error and
rejected``. Aggregates give, per model and overall, the natural error rate, the
catch rate of the governed path on natural errors, and the false-rejection rate
on correct claims.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from ..compiler import ExecutionPlan
from ..ledger import JsonlLedger
from .episode import Episode, EpisodeError, parse_episode, replay_episode
from .harness import RunResult
from .recompute import Recomputer
from .workspace import Workspace

NATURAL_STUDY_SCHEMA = "contractplane.dev/experimental/natural-study/v0"
NATURAL_SCALE_STUDY_SCHEMA = "contractplane.dev/experimental/natural-scale-study/v0"
NATURAL_POWER_STUDY_SCHEMA = "contractplane.dev/experimental/natural-power-study/v0"
NATURAL_CONDITION = "natural"
DATASET_TOKENS: dict[str, str] = {"a": "hard-count-a", "b": "hard-count-b"}
# The scale grid reuses the SAME counting rule as hard-count-a (nested-groups),
# growing only the record count so scale is the single variable.
DATASET_SCALE_TOKENS: dict[str, str] = {
    "c": "hard-count-c",
    "d": "hard-count-d",
    "e": "hard-count-e",
}
# The shortcut-closed scale grid: same rule and scales as c/d/e, but with random
# ids and irregular group sizes so the count cannot be read off a last id or a
# uniform group multiplier. See scripts/generate_hard_scale2_datasets.py.
DATASET_SCALE2_TOKENS: dict[str, str] = {
    "f": "hard-count-f",
    "g": "hard-count-g",
    "h": "hard-count-h",
}
# Independent datasets at the two error-prone bands (different seeds, same rule and
# band) so a scale-band effect is not confounded with a single dataset's identity.
# Band g now = {g, g2, g3}; band h = {h, h2, h3}.
DATASET_SCALE3_TOKENS: dict[str, str] = {
    "g2": "hard-count-g2",
    "g3": "hard-count-g3",
    "h2": "hard-count-h2",
    "h3": "hard-count-h3",
}
ATTEMPTS: tuple[str, ...] = ("1", "2")
NATURAL_STUDY_NOTE = (
    "EXPERIMENTAL spontaneous-error study. Unlike the instructed adversarial grid, "
    "these episodes record a genuine tool-less counting attempt on a hard-but-fair "
    "dataset; any error is natural, not instructed. Rows derive from real replayed "
    "episodes only; placeholder slots are skipped, never fabricated. Only "
    "real-recorded episodes are evidence."
)
NATURAL_SCALE_STUDY_NOTE = (
    "EXPERIMENTAL spontaneous-error SCALE study. Same tool-less honesty protocol and "
    "same nested-groups counting rule as the natural grid, but the dataset size grows "
    "(c ~ 300, d ~ 800, e ~ 1500 records) until natural errors emerge -- standard "
    "capability-frontier evaluation practice. Rows derive from real replayed episodes "
    "only; placeholder slots are skipped, never fabricated."
)
NATURAL_SCALE2_STUDY_NOTE = (
    "EXPERIMENTAL spontaneous-error SCALE study, SHORTCUT-CLOSED variant. Same rule and "
    "scales as c/d/e (f ~ 300, g ~ 800, h ~ 1500 records) but with random ids and "
    "irregular group sizes, because c/d/e admitted O(1)/O(groups) shortcuts (sequential "
    "ids whose last value revealed the count; uniform 13-record groups) that recorded "
    "responses confirmed models exploited. Here the count can only be obtained by "
    "enumeration. Rows derive from real replayed episodes only; placeholders are skipped."
)
NATURAL_POWER_STUDY_NOTE = (
    "EXPERIMENTAL spontaneous-error POWER study. Merges every natural episode over the "
    "shortcut-closed hard datasets across two mechanically recomputable task families -- "
    "counting (f/g/h, with repeated attempts to raise N at g and h) and aggregate/sum "
    "(g/h) -- and reports, per family / scale / model, the sample size N, the natural "
    "error rate with a Wilson 95% binomial confidence interval, the error-magnitude "
    "distribution, the governed path's catch rate on natural errors, and the "
    "false-rejection rate on correct claims. Rows derive from real replayed episodes "
    "only; placeholder slots are skipped, never fabricated."
)
LOCAL_STUDY_SCHEMA = "contractplane.dev/experimental/local-model-study/v0"
LOCAL_STUDY_NOTE = (
    "EXPERIMENTAL spontaneous-error study on a LOCAL model. Same tool-less honesty "
    "protocol and same shortcut-closed nested-groups counting rule as the frontier "
    "natural grids, but recorded from a locally-hosted small model (qwen3:8b via ollama) "
    "at zero API cost, which lets N grow to ~20 attempts per dataset. Each attempt varies "
    "the sampling seed/temperature for independence; whatever the model claims is recorded "
    "verbatim. An attempt whose response yields no parsable count is recorded as a "
    "parse-failure -- counted as its own category, never retried-until-parse and never "
    "scored as a caught error. Rows derive from real replayed episodes only. This study "
    "extends the capability-frontier characterization (C10) below the frontier tier: it "
    "measures whether natural error rate rises as model capability falls while the "
    "recomputation gate's catch rate and 0% false-rejection rate hold at large N."
)
# Recorded frontier per-model natural error counts (errors / episodes) from the sibling
# Anthropic-model grids, held here so the local study can emit a capability-frontier
# comparison block. Ordered strongest -> weakest frontier tier.
FRONTIER_NATURAL_RATES: dict[str, dict[str, int]] = {
    "opus": {"errors": 2, "episodes": 13},
    "sonnet": {"errors": 4, "episodes": 13},
    "haiku": {"errors": 7, "episodes": 13},
}


class HardCountRecomputer:
    """Recompute the true record count of a hard dataset from the raw data.

    Ground truth is derived from the caller-owned dataset named by the flow input,
    never trusted from the recorder's artifact. Two structural conventions are
    supported by one mechanical rule (documented verbatim in the study README):

    * ``hard-count-a`` (``structure: nested-groups``): a *record* is an element of
      ``groups[*].items[*]`` whose ``kind`` equals ``"record"``. Items with
      ``kind == "metadata"`` are not records even though they share the shape.
      Two records that share an ``id`` (near-duplicates) are each counted.
    * ``hard-count-b`` (``structure: flat-ledger``): a *record* is an element of
      the top-level ``ledger`` array whose ``role`` equals ``"data"``. Rows with
      ``role`` of ``"annotation"`` or ``"subtotal"`` are not records.

    The count is exposed as the ``rows`` field the ``report`` flow already checks,
    so a natural over- or under-count is rejected by recomputation exactly as an
    instructed overclaim would be.
    """

    def __init__(
        self,
        datasets_dir: Path,
        *,
        evidence_ids: frozenset[str] = frozenset({"report-artifact"}),
        dataset_key: str = "dataset",
        expect_field: str = "rows",
    ) -> None:
        self.datasets_dir = Path(datasets_dir)
        self.evidence_ids = evidence_ids
        self.dataset_key = dataset_key
        self.expect_field = expect_field

    @staticmethod
    def count_records(data: dict[str, Any]) -> int | None:
        """Apply the documented counting rule; ``None`` if the shape is unknown."""
        groups = data.get("groups")
        if isinstance(groups, list):
            total = 0
            for group in groups:
                if not isinstance(group, dict):
                    return None
                items = group.get("items", [])
                if not isinstance(items, list):
                    return None
                total += sum(
                    1
                    for item in items
                    if isinstance(item, dict) and item.get("kind") == "record"
                )
            return total
        ledger = data.get("ledger")
        if isinstance(ledger, list):
            return sum(
                1
                for row in ledger
                if isinstance(row, dict) and row.get("role") == "data"
            )
        return None

    def recompute(
        self, stage: Any, evidence_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any] | None:
        if evidence_id not in self.evidence_ids:
            return None
        dataset = (inputs or {}).get(self.dataset_key)
        if not isinstance(dataset, str) or not dataset:
            return None
        source = self.datasets_dir / f"{dataset}.json"
        if not source.is_file():
            return None
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        count = self.count_records(data)
        if count is None:
            return None
        return {self.expect_field: count}


class HardSumRecomputer:
    """Recompute the true SUM of a numeric field over a hard dataset's records.

    Ground truth for the natural aggregate (sum) family. It totals the documented
    numeric field (``value`` by default) of every record item (``kind ==
    "record"``) across all nested groups, derived from the caller-owned dataset,
    never trusted from the recorder's artifact. Metadata items carry no ``value``
    and are excluded; near-duplicate records (sharing an ``id``) each contribute
    their value, so the sum is consistent with the record count. The total is
    exposed as the ``total`` field the ``aggregate`` flow already checks, so a
    natural over- or under-sum is rejected by recomputation.
    """

    def __init__(
        self,
        datasets_dir: Path,
        *,
        evidence_ids: frozenset[str] = frozenset({"aggregate-artifact"}),
        dataset_key: str = "dataset",
        value_field: str = "value",
        expect_field: str = "total",
    ) -> None:
        self.datasets_dir = Path(datasets_dir)
        self.evidence_ids = evidence_ids
        self.dataset_key = dataset_key
        self.value_field = value_field
        self.expect_field = expect_field

    def sum_records(self, data: dict[str, Any]) -> int | None:
        """Total the record ``value`` field across nested groups; ``None`` if unknown."""
        groups = data.get("groups")
        if not isinstance(groups, list):
            return None
        total = 0
        for group in groups:
            if not isinstance(group, dict):
                return None
            items = group.get("items", [])
            if not isinstance(items, list):
                return None
            for item in items:
                if not isinstance(item, dict) or item.get("kind") != "record":
                    continue
                value = item.get(self.value_field)
                if not isinstance(value, int) or isinstance(value, bool):
                    return None
                total += value
        return total

    def recompute(
        self, stage: Any, evidence_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any] | None:
        if evidence_id not in self.evidence_ids:
            return None
        dataset = (inputs or {}).get(self.dataset_key)
        if not isinstance(dataset, str) or not dataset:
            return None
        source = self.datasets_dir / f"{dataset}.json"
        if not source.is_file():
            return None
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        total = self.sum_records(data)
        if total is None:
            return None
        return {self.expect_field: total}


def parse_natural_filename(filename: str) -> tuple[str, str, str]:
    """Split ``episode-<model>-<a|b>-<attempt>.json`` into ``(model, dataset, attempt)``.

    ``dataset`` is returned as the full dataset name (``hard-count-a`` /
    ``hard-count-b``) resolved from the ``a``/``b`` token; the attempt is kept as a
    string. Model shorts may not contain hyphens.
    """
    stem = filename
    if stem.startswith("episode-"):
        stem = stem[len("episode-"):]
    if stem.endswith(".json"):
        stem = stem[: -len(".json")]
    parts = stem.rsplit("-", 2)
    if len(parts) != 3:
        return stem, "?", "?"
    model, token, attempt = parts
    dataset = DATASET_TOKENS.get(token, token)
    return model, dataset, attempt


def parse_scale_filename(
    filename: str, scale_tokens: dict[str, str] = DATASET_SCALE_TOKENS
) -> tuple[str, str, str, str]:
    """Split a scale filename into ``(model, scale, dataset, attempt)``.

    Two forms are accepted:

    * ``episode-<model>-<scale>.json`` -> the first attempt (``attempt == "1"``);
    * ``episode-<model>-<scale>-r<N>.json`` -> a REPETITION, ``attempt == "<N>"``.

    ``scale`` is the raw scale token; ``dataset`` is the full dataset name it
    resolves to via ``scale_tokens`` (defaults to the c/d/e grid; pass
    ``DATASET_SCALE2_TOKENS`` for the shortcut-closed f/g/h grid). Model shorts may
    not contain hyphens.
    """
    stem = filename
    if stem.startswith("episode-"):
        stem = stem[len("episode-"):]
    if stem.endswith(".json"):
        stem = stem[: -len(".json")]

    attempt = "1"
    head, sep, tail = stem.rpartition("-")
    if sep and len(tail) >= 2 and tail[0] == "r" and tail[1:].isdigit():
        attempt = tail[1:]
        stem = head

    parts = stem.rsplit("-", 1)
    if len(parts) != 2:
        return stem, "?", "?", attempt
    model, scale = parts
    dataset = scale_tokens.get(scale, scale)
    return model, scale, dataset, attempt


def _natural_row(
    episode: Episode,
    *,
    plan: ExecutionPlan,
    pack_dir: Path,
    recomputer: HardCountRecomputer | Recomputer,
) -> dict[str, Any]:
    stage = plan.stages[0]
    evidence_id = stage.requires_evidence[0] if stage.requires_evidence else None
    expected = (
        recomputer.recompute(stage, evidence_id, episode.inputs) if evidence_id else None
    )
    field = next(iter(expected)) if expected else None
    artifact = episode.artifacts.get(evidence_id, {}) if evidence_id else {}
    claimed = artifact.get(field) if field else None
    truth = expected.get(field) if expected else None

    with tempfile.TemporaryDirectory(prefix="natural-study-") as scratch:
        root = Path(scratch)
        report = replay_episode(
            episode,
            plan=plan,
            pack_dir=pack_dir,
            workspace=Workspace.create(root / "ws"),
            ledger=JsonlLedger(root / "ledger.jsonl"),
            execution_id="natural-study",
            recomputer=recomputer,
        )

    verdict_obj = report.verdicts[-1] if report.verdicts else None
    schema_gate = (
        "fail"
        if (verdict_obj and not verdict_obj.accepted and verdict_obj.method == "schema")
        else "pass"
    )
    rejected = report.result is not RunResult.SUCCEEDED
    error = claimed != truth
    absolute_error = (
        abs(claimed - truth)
        if isinstance(claimed, int)
        and isinstance(truth, int)
        and not isinstance(claimed, bool)
        else None
    )
    return {
        "checkedField": field,
        "claimed": claimed,
        "truth": truth,
        "error": bool(error),
        "absoluteError": absolute_error,
        "schema_gate": schema_gate,
        "verdict_method": verdict_obj.method if verdict_obj else None,
        "verdict": "rejected" if rejected else "accepted",
        "caught": bool(error and rejected),
        "citable": episode.citable,
    }


def _status(entry: dict[str, Any]) -> str:
    if "skipped" in entry:
        return "skipped"
    if "fault" in entry:
        return "fault"
    return "recorded"


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _model_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recorded = [r for r in rows if _status(r) == "recorded"]
    errors = [r for r in recorded if r.get("error")]
    correct = [r for r in recorded if not r.get("error")]
    caught = [r for r in errors if r.get("caught")]
    missed = [r for r in errors if not r.get("caught")]
    false_rejections = [r for r in correct if r.get("verdict") == "rejected"]
    return {
        "recorded": len(recorded),
        "skipped": sum(1 for r in rows if _status(r) == "skipped"),
        "fault": sum(1 for r in rows if _status(r) == "fault"),
        "correct": len(correct),
        "errors": len(errors),
        "naturalErrorRate": _rate(len(errors), len(recorded)),
        "caught": len(caught),
        "missed": len(missed),
        "catchRateOnErrors": _rate(len(caught), len(errors)),
        "falseRejections": len(false_rejections),
        "falseRejectionRateOnCorrect": _rate(len(false_rejections), len(correct)),
    }


def _aggregate(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    models = sorted({e.get("model") or "?" for e in episodes})
    per_model = {m: _model_stats([e for e in episodes if e.get("model") == m]) for m in models}
    overall = _model_stats(episodes)
    return {"overall": overall, "perModel": per_model}


def run_natural_study(
    study_dir: str | Path,
    *,
    pack_dir: Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
) -> dict[str, Any]:
    """Replay the natural grid and aggregate spontaneous-error catch rates."""
    study_dir = Path(study_dir)
    episodes: list[dict[str, Any]] = []
    for path in sorted(study_dir.glob("episode-*.json")):
        model, dataset, attempt = parse_natural_filename(path.name)
        entry: dict[str, Any] = {
            "file": path.name,
            "model": model,
            "dataset": dataset,
            "attempt": attempt,
            "condition": NATURAL_CONDITION,
            "instructed": False,
        }
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["fault"] = f"unreadable episode: {exc}"
            episodes.append(entry)
            continue
        if raw.get("provenance") == "placeholder" or raw.get("status") == "unrecorded":
            entry["skipped"] = "unrecorded"
            episodes.append(entry)
            continue
        try:
            episode = parse_episode(raw, source=path.name)
            entry.update(
                _natural_row(episode, plan=plan, pack_dir=pack_dir, recomputer=recomputer)
            )
        except EpisodeError as exc:
            entry["fault"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - a replay fault is a study result, not a crash
            entry["fault"] = f"replay failed: {exc}"
        episodes.append(entry)

    return {
        "schema": NATURAL_STUDY_SCHEMA,
        "note": NATURAL_STUDY_NOTE,
        "condition": NATURAL_CONDITION,
        "instructed": False,
        "studyDir": str(study_dir),
        "datasets": sorted(DATASET_TOKENS.values()),
        "models": sorted({e.get("model") or "?" for e in episodes}),
        "episodes": episodes,
        "aggregate": _aggregate(episodes),
    }


def write_natural_study(report: dict[str, Any], out_path: str | Path) -> Path:
    target = Path(out_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _scale_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The natural rates, plus mean absolute error over recorded errors."""
    stats = _model_stats(rows)
    magnitudes = [
        r["absoluteError"]
        for r in rows
        if _status(r) == "recorded" and r.get("error") and isinstance(r.get("absoluteError"), int)
    ]
    stats["meanAbsoluteError"] = (
        round(sum(magnitudes) / len(magnitudes), 4) if magnitudes else None
    )
    return stats


def _scale_aggregate(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    models = sorted({e.get("model") or "?" for e in episodes})
    scales = sorted({e.get("scale") or "?" for e in episodes})
    return {
        "overall": _scale_stats(episodes),
        "perModel": {m: _scale_stats([e for e in episodes if e.get("model") == m]) for m in models},
        "perScale": {s: _scale_stats([e for e in episodes if e.get("scale") == s]) for s in scales},
    }


def run_natural_scale_study(
    study_dir: str | Path,
    *,
    pack_dir: Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    scale_tokens: dict[str, str] = DATASET_SCALE_TOKENS,
    note: str = NATURAL_SCALE_STUDY_NOTE,
) -> dict[str, Any]:
    """Replay a scale grid and aggregate spontaneous-error rates per scale and model.

    Structurally identical to :func:`run_natural_study` but keyed on the
    ``episode-<model>-<scale>.json`` grid (one attempt per model x scale) and
    aggregated ``perScale`` as well as ``perModel``, so the study can show whether
    the natural error rate rises with dataset size while the governed path's catch
    rate holds. ``scale_tokens`` selects the grid: the default c/d/e grid, or
    ``DATASET_SCALE2_TOKENS`` for the shortcut-closed f/g/h grid.
    """
    study_dir = Path(study_dir)
    episodes: list[dict[str, Any]] = []
    for path in sorted(study_dir.glob("episode-*.json")):
        model, scale, dataset, attempt = parse_scale_filename(path.name, scale_tokens)
        entry: dict[str, Any] = {
            "file": path.name,
            "model": model,
            "scale": scale,
            "dataset": dataset,
            "attempt": attempt,
            "condition": NATURAL_CONDITION,
            "instructed": False,
        }
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["fault"] = f"unreadable episode: {exc}"
            episodes.append(entry)
            continue
        if raw.get("provenance") == "placeholder" or raw.get("status") == "unrecorded":
            entry["skipped"] = "unrecorded"
            episodes.append(entry)
            continue
        try:
            episode = parse_episode(raw, source=path.name)
            entry.update(
                _natural_row(episode, plan=plan, pack_dir=pack_dir, recomputer=recomputer)
            )
        except EpisodeError as exc:
            entry["fault"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - a replay fault is a study result, not a crash
            entry["fault"] = f"replay failed: {exc}"
        episodes.append(entry)

    return {
        "schema": NATURAL_SCALE_STUDY_SCHEMA,
        "note": note,
        "condition": NATURAL_CONDITION,
        "instructed": False,
        "studyDir": str(study_dir),
        "scales": sorted(scale_tokens),
        "datasets": sorted(scale_tokens.values()),
        "models": sorted({e.get("model") or "?" for e in episodes}),
        "episodes": episodes,
        "aggregate": _scale_aggregate(episodes),
    }


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion (default 95%).

    Returns ``(low, high)`` clamped to ``[0, 1]``, or ``(None, None)`` when there
    is no sample. The Wilson interval is used rather than the normal approximation
    because it behaves well for the small N and near-0/near-1 rates this study
    produces.
    """
    if n <= 0:
        return (None, None)
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return (round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))


def _hypergeom_pmf(x: int, row1: int, col1: int, total: int) -> float:
    """P(cell(1,1) == x) for a 2x2 table with the given fixed margins."""
    return math.comb(col1, x) * math.comb(total - col1, row1 - x) / math.comb(total, row1)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float | None:
    """Two-sided Fisher exact p-value for the 2x2 table [[a, b], [c, d]].

    Pure combinatorics (no scipy): sums the hypergeometric probability of every
    table with the same margins that is no more likely than the observed one. Rows
    are the two groups, column 1 is the "event" count. Returns ``None`` for an empty
    table.
    """
    row1, row2 = a + b, c + d
    col1, total = a + c, a + b + c + d
    if total == 0 or row1 == 0 or row2 == 0 or col1 == 0 or (total - col1) == 0:
        return None
    p_obs = _hypergeom_pmf(a, row1, col1, total)
    lo = max(0, row1 - (total - col1))
    hi = min(row1, col1)
    tail = sum(
        p for x in range(lo, hi + 1)
        if (p := _hypergeom_pmf(x, row1, col1, total)) <= p_obs * (1 + 1e-9)
    )
    return round(min(1.0, tail), 6)


def _pairwise_model_fisher(by_model: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Two-sided Fisher exact p for every pair of models on error vs non-error counts.

    Tests whether the per-model natural error *rates* differ more than chance; cited
    so the paper can state (non-)significance honestly rather than eyeballing rates.
    """
    models = sorted(m for m, s in by_model.items() if s.get("recorded", s.get("N", 0)))
    out: dict[str, Any] = {}
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            m1, m2 = models[i], models[j]
            e1, n1 = by_model[m1]["errors"], by_model[m1]["N"]
            e2, n2 = by_model[m2]["errors"], by_model[m2]["N"]
            out[f"{m1}_vs_{m2}"] = {
                "counts": {m1: f"{e1}/{n1}", m2: f"{e2}/{n2}"},
                "table": [[e1, n1 - e1], [e2, n2 - e2]],
                "pValueTwoSided": fisher_exact_two_sided(e1, n1 - e1, e2, n2 - e2),
            }
    return out


def _error_magnitudes(rows: list[dict[str, Any]]) -> list[int]:
    return sorted(
        r["absoluteError"]
        for r in rows
        if _status(r) == "recorded" and r.get("error") and isinstance(r.get("absoluteError"), int)
    )


def _power_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Natural rates with a Wilson 95% CI and an error-magnitude distribution."""
    stats = _model_stats(rows)
    n = stats["recorded"]
    errors = stats["errors"]
    low, high = wilson_interval(errors, n)
    magnitudes = _error_magnitudes(rows)
    stats["N"] = n
    stats["errorRateWilson95"] = {
        "point": stats["naturalErrorRate"],
        "low": low,
        "high": high,
    }
    stats["errorMagnitude"] = {
        "n": len(magnitudes),
        "values": magnitudes,
        "min": magnitudes[0] if magnitudes else None,
        "max": magnitudes[-1] if magnitudes else None,
        "mean": round(sum(magnitudes) / len(magnitudes), 4) if magnitudes else None,
        "median": _median(magnitudes),
    }
    return stats


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return round((ordered[mid - 1] + ordered[mid]) / 2, 4)


def scale_band(scale: str) -> str:
    """The scale band a scale token belongs to: ``g2``/``g3`` -> ``g``, ``h2`` -> ``h``.

    A band groups the independent datasets drawn at the same scale (different seeds,
    same rule and record-count band), so a scale-band effect measured across it is
    not confounded with a single dataset's identity.
    """
    return scale.rstrip("0123456789") or scale


def _power_aggregate(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    families = sorted({e.get("family") or "?" for e in episodes})
    scales = sorted({e.get("scale") or "?" for e in episodes})
    models = sorted({e.get("model") or "?" for e in episodes})
    bands = sorted({e.get("band") or "?" for e in episodes})
    datasets = sorted({e.get("dataset") or "?" for e in episodes})
    family_scales = sorted({f"{e.get('family')}/{e.get('scale')}" for e in episodes})
    band_models = sorted({f"{e.get('band')}/{e.get('model')}" for e in episodes})
    return {
        "overall": _power_stats(episodes),
        "byFamily": {f: _power_stats([e for e in episodes if e.get("family") == f]) for f in families},
        "byScale": {s: _power_stats([e for e in episodes if e.get("scale") == s]) for s in scales},
        "byModel": {m: _power_stats([e for e in episodes if e.get("model") == m]) for m in models},
        "byFamilyScale": {
            fs: _power_stats(
                [e for e in episodes if f"{e.get('family')}/{e.get('scale')}" == fs]
            )
            for fs in family_scales
        },
        # A scale BAND pools several independent datasets, so its pooled Wilson CI
        # mixes heterogeneous sources -- reported, but flagged; the per-band-per-model
        # rates below are the primary, homogeneous unit.
        "byBand": {b: _power_stats([e for e in episodes if e.get("band") == b]) for b in bands},
        "byBandModel": {
            bm: _power_stats([e for e in episodes if f"{e.get('band')}/{e.get('model')}" == bm])
            for bm in band_models
        },
        "byDataset": {d: _power_stats([e for e in episodes if e.get("dataset") == d]) for d in datasets},
        # Two-sided Fisher exact tests on per-model error vs non-error counts, so the
        # paper can state per-model (non-)significance honestly instead of eyeballing.
        "pairwiseModelErrorFisher": _pairwise_model_fisher(
            {m: _power_stats([e for e in episodes if e.get("model") == m]) for m in models}
        ),
        "note": (
            "byBand pools independent datasets at a scale; its pooled CI is heterogeneous. "
            "byBandModel (per band x model) is the primary homogeneous rate. byDataset shows "
            "each independent dataset separately so a band effect is visibly not one dataset's identity. "
            "pairwiseModelErrorFisher gives exact two-sided p-values for per-model error-rate differences."
        ),
    }


def _power_grid_rows(
    study_dir: Path,
    *,
    family: str,
    pack_dir: Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | HardSumRecomputer | Recomputer,
    scale_tokens: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    study_dir = Path(study_dir)
    for path in sorted(study_dir.glob("episode-*.json")):
        model, scale, dataset, attempt = parse_scale_filename(path.name, scale_tokens)
        entry: dict[str, Any] = {
            "file": path.name,
            "family": family,
            "model": model,
            "scale": scale,
            "band": scale_band(scale),
            "dataset": dataset,
            "attempt": attempt,
            "condition": NATURAL_CONDITION,
            "instructed": False,
        }
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["fault"] = f"unreadable episode: {exc}"
            rows.append(entry)
            continue
        if raw.get("provenance") == "placeholder" or raw.get("status") == "unrecorded":
            entry["skipped"] = "unrecorded"
            rows.append(entry)
            continue
        try:
            episode = parse_episode(raw, source=path.name)
            entry.update(_natural_row(episode, plan=plan, pack_dir=pack_dir, recomputer=recomputer))
        except EpisodeError as exc:
            entry["fault"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - a replay fault is a study result, not a crash
            entry["fault"] = f"replay failed: {exc}"
        rows.append(entry)
    return rows


def run_natural_power_study(
    *,
    pack_dir: Path,
    count_dir: str | Path,
    count_plan: ExecutionPlan,
    count_recomputer: HardCountRecomputer | Recomputer,
    aggregate_dir: str | Path,
    aggregate_plan: ExecutionPlan,
    aggregate_recomputer: HardSumRecomputer | Recomputer,
    scale_tokens: dict[str, str] = DATASET_SCALE2_TOKENS,
    extra_count_grids: list[tuple[str | Path, dict[str, str]]] | None = None,
) -> dict[str, Any]:
    """Merge every natural episode across the counting and aggregate families.

    Replays the shortcut-closed counting grid (f/g/h, including ``-rN`` repetition
    slots), any ``extra_count_grids`` (each a ``(dir, scale_tokens)`` pair -- e.g.
    the independent per-band datasets g2/g3/h2/h3), and the aggregate/sum grid
    (g/h) through the governed kernel path. It then aggregates per family / scale /
    model / **scale band** with Wilson 95% CIs and error-magnitude distributions;
    a scale band pools several independent datasets so its effect is not confounded
    with one dataset's identity. Placeholders skip honestly; nothing is fabricated.
    """
    episodes = _power_grid_rows(
        count_dir, family="count", pack_dir=pack_dir, plan=count_plan,
        recomputer=count_recomputer, scale_tokens=scale_tokens,
    )
    for extra_dir, extra_tokens in extra_count_grids or []:
        episodes += _power_grid_rows(
            extra_dir, family="count", pack_dir=pack_dir, plan=count_plan,
            recomputer=count_recomputer, scale_tokens=extra_tokens,
        )
    episodes += _power_grid_rows(
        aggregate_dir, family="aggregate", pack_dir=pack_dir, plan=aggregate_plan,
        recomputer=aggregate_recomputer, scale_tokens=scale_tokens,
    )
    return {
        "schema": NATURAL_POWER_STUDY_SCHEMA,
        "note": NATURAL_POWER_STUDY_NOTE,
        "condition": NATURAL_CONDITION,
        "instructed": False,
        "families": ["count", "aggregate"],
        "countDir": str(count_dir),
        "extraCountDirs": [str(d) for d, _ in extra_count_grids or []],
        "aggregateDir": str(aggregate_dir),
        "models": sorted({e.get("model") or "?" for e in episodes}),
        "scales": sorted({e.get("scale") or "?" for e in episodes}),
        "bands": sorted({e.get("band") or "?" for e in episodes}),
        "datasets": sorted({e.get("dataset") or "?" for e in episodes}),
        "episodes": episodes,
        "aggregate": _power_aggregate(episodes),
    }


def _local_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Power-study stats over the *scored* rows, plus a separate parse-failure count.

    Parse-failure rows carry no genuine claim (the model produced no parsable count),
    so they are excluded from the error/catch/false-rejection math -- feeding them
    through replay would fail the ``rows >= 1`` evidence schema and be miscounted as a
    caught miscount, conflating "no count" with "wrong count". They are reported as
    their own ``parseFailures`` tally instead.
    """
    parse_failures = [r for r in rows if r.get("parseFailure")]
    considered = [r for r in rows if not r.get("parseFailure")]
    stats = _power_stats(considered)
    stats["parseFailures"] = len(parse_failures)
    return stats


def _frontier_comparison(local_overall: dict[str, Any]) -> dict[str, Any]:
    """Capability-frontier comparison: recorded frontier rates + this local run.

    Places the local (weaker) model alongside the recorded Anthropic-model natural
    error rates so the paper can show error rate scaling by capability tier. The
    frontier numbers are the sibling grids' recorded counts (not recomputed here).
    """
    tiers = [
        {
            "model": model,
            "tier": "frontier",
            "errors": rate["errors"],
            "episodes": rate["episodes"],
            "naturalErrorRate": _rate(rate["errors"], rate["episodes"]),
        }
        for model, rate in FRONTIER_NATURAL_RATES.items()
    ]
    local_tier = {
        "model": "qwen3:8b",
        "tier": "local-small",
        "errors": local_overall.get("errors"),
        "episodes": local_overall.get("recorded"),
        "naturalErrorRate": local_overall.get("naturalErrorRate"),
        "catchRateOnErrors": local_overall.get("catchRateOnErrors"),
        "falseRejections": local_overall.get("falseRejections"),
        "parseFailures": local_overall.get("parseFailures"),
    }
    return {
        "note": (
            "Natural error rate by model-capability tier: recorded frontier grids "
            "(opus/sonnet/haiku) vs this local small-model run. Frontier counts are the "
            "sibling grids' recorded values; the local row is recomputed from this study."
        ),
        "byTier": tiers + [local_tier],
    }


def run_local_study(
    study_dir: str | Path,
    *,
    pack_dir: Path,
    plan: ExecutionPlan,
    recomputer: HardCountRecomputer | Recomputer,
    model: str = "qwen3:8b",
) -> dict[str, Any]:
    """Replay a large-N local-model harvest through the identical governed path.

    Iterates ``episode-*.json`` in ``study_dir``, replays every episode that carries a
    real claim through :func:`_natural_row` (dispatch -> claim -> recompute-verify ->
    verdict, the same path the frontier grids use), routes ``parseFailure`` episodes to
    a separate tally, and aggregates overall and per dataset with Wilson 95% CIs and an
    error-magnitude distribution (via :func:`_power_stats`). Also emits a
    capability-frontier comparison block. Dataset/model are read from episode *content*,
    not the filename, so the many-attempts-per-dataset local layout needs no filename
    grammar. Placeholders skip honestly; nothing is fabricated.
    """
    study_dir = Path(study_dir)
    episodes: list[dict[str, Any]] = []
    for path in sorted(study_dir.glob("episode-*.json")):
        entry: dict[str, Any] = {"file": path.name}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["fault"] = f"unreadable episode: {exc}"
            episodes.append(entry)
            continue
        entry["model"] = raw.get("model")
        entry["dataset"] = raw.get("dataset")
        entry["attempt"] = raw.get("attempt")
        entry["condition"] = raw.get("condition")
        entry["instructed"] = bool(raw.get("instructed", False))
        if raw.get("provenance") == "placeholder" or raw.get("status") == "unrecorded":
            entry["skipped"] = "unrecorded"
            episodes.append(entry)
            continue
        if raw.get("parseFailure"):
            # Recorded data on small-model behaviour, but not a scored counting attempt.
            entry["parseFailure"] = True
            entry["claimed"] = None
            episodes.append(entry)
            continue
        try:
            episode = parse_episode(raw, source=path.name)
            entry.update(_natural_row(episode, plan=plan, pack_dir=pack_dir, recomputer=recomputer))
        except EpisodeError as exc:
            entry["fault"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - a replay fault is a study result, not a crash
            entry["fault"] = f"replay failed: {exc}"
        episodes.append(entry)

    datasets = sorted({e.get("dataset") for e in episodes if e.get("dataset")})
    overall = _local_stats(episodes)
    aggregate = {
        "overall": overall,
        "perDataset": {
            d: _local_stats([e for e in episodes if e.get("dataset") == d]) for d in datasets
        },
        "frontierComparison": _frontier_comparison(overall),
    }
    return {
        "schema": LOCAL_STUDY_SCHEMA,
        "note": LOCAL_STUDY_NOTE,
        "condition": NATURAL_CONDITION,
        "instructed": False,
        "model": model,
        "studyDir": str(study_dir),
        "datasets": datasets,
        "models": sorted({e.get("model") or "?" for e in episodes}),
        "episodes": episodes,
        "aggregate": aggregate,
    }


def _example_paths() -> tuple[Path, Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[3]
    pack_dir = repo_root / "examples" / "governed-run"
    study_dir = pack_dir / "episodes" / "study-natural"
    out = repo_root / "artifacts" / "natural_study.json"
    return repo_root, pack_dir, study_dir, out


def main(argv: list[str] | None = None) -> int:
    from ..compiler import compile_plan
    from ..loader import load_domain_pack

    repo_root, pack_dir_default, study_dir_default, out_default = _example_paths()
    scale_dir_default = pack_dir_default / "episodes" / "study-natural-scale"
    scale_out_default = repo_root / "artifacts" / "natural_scale_study.json"
    scale2_dir_default = pack_dir_default / "episodes" / "study-natural-scale2"
    scale2_out_default = repo_root / "artifacts" / "natural_scale2_study.json"
    aggregate_dir_default = pack_dir_default / "episodes" / "study-natural-aggregate"
    scale3_dir_default = pack_dir_default / "episodes" / "study-natural-scale3"
    power_out_default = repo_root / "artifacts" / "natural_power_study.json"
    parser = argparse.ArgumentParser(
        description="Replay the spontaneous-error (natural) episode study and aggregate results."
    )
    grid = parser.add_mutually_exclusive_group()
    grid.add_argument(
        "--scale",
        action="store_true",
        help="run the SCALE grid (episodes/study-natural-scale, c/d/e) instead of the a/b grid",
    )
    grid.add_argument(
        "--scale2",
        action="store_true",
        help="run the shortcut-closed SCALE grid (episodes/study-natural-scale2, f/g/h)",
    )
    grid.add_argument(
        "--power",
        action="store_true",
        help="run the POWER study: merge f/g/h counting (incl. repetitions) + aggregate/sum",
    )
    parser.add_argument("--dir", default=None, help="study fixture directory (overrides the grid default)")
    parser.add_argument("--pack", default=str(pack_dir_default), help="domain pack directory")
    parser.add_argument("--out", default=None, help="output JSON path (overrides the grid default)")
    args = parser.parse_args(argv)

    pack_dir = Path(args.pack)
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="report")
    recomputer = HardCountRecomputer(pack_dir / "datasets")

    if args.power:
        count_dir = Path(args.dir) if args.dir else scale2_dir_default
        out = Path(args.out) if args.out else power_out_default
        report = run_natural_power_study(
            pack_dir=pack_dir,
            count_dir=count_dir,
            count_plan=plan,
            count_recomputer=recomputer,
            aggregate_dir=aggregate_dir_default,
            aggregate_plan=compile_plan(pack, entrypoint_id="aggregate"),
            aggregate_recomputer=HardSumRecomputer(pack_dir / "datasets"),
            extra_count_grids=[(scale3_dir_default, DATASET_SCALE3_TOKENS)],
        )
        target = write_natural_study(report, out)
        overall = report["aggregate"]["overall"]
        print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2, sort_keys=True))
        print(
            f"\nnatural power study: N={overall['N']} recorded "
            f"({overall['errors']} natural errors, {overall['caught']} caught, "
            f"{overall['missed']} missed, {overall['falseRejections']} false-rejections), "
            f"{overall['skipped']} skipped, {overall['fault']} fault -> {target}"
        )
        return 0

    if args.scale2:
        study_dir = Path(args.dir) if args.dir else scale2_dir_default
        out = Path(args.out) if args.out else scale2_out_default
        report = run_natural_scale_study(
            study_dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer,
            scale_tokens=DATASET_SCALE2_TOKENS, note=NATURAL_SCALE2_STUDY_NOTE,
        )
        label = "natural scale study (shortcut-closed f/g/h)"
    elif args.scale:
        study_dir = Path(args.dir) if args.dir else scale_dir_default
        out = Path(args.out) if args.out else scale_out_default
        report = run_natural_scale_study(study_dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer)
        label = "natural scale study"
    else:
        study_dir = Path(args.dir) if args.dir else study_dir_default
        out = Path(args.out) if args.out else out_default
        report = run_natural_study(study_dir, pack_dir=pack_dir, plan=plan, recomputer=recomputer)
        label = "natural study"
    target = write_natural_study(report, out)

    overall = report["aggregate"]["overall"]
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"\n{label}: {overall['recorded']} recorded "
        f"({overall['errors']} natural errors, {overall['caught']} caught, "
        f"{overall['missed']} missed, {overall['falseRejections']} false-rejections), "
        f"{overall['skipped']} skipped, {overall['fault']} fault -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
