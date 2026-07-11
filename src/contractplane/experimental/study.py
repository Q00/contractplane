"""Batch episode-study runner and aggregation.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

A single replayed episode is near-tautological evidence, and a single task family
is narrow. This module turns the episode mechanism into a small *study* across
three mechanically recomputable task families (``count``, ``aggregate``,
``filtercount``): it replays every recorded producer episode in a directory
through the same governed kernel path, records one row per episode (claim vs
recomputed ground truth, schema gate, verdict, whether the unit advanced), and
aggregates the results into a ``family x model x condition`` table.

It never fabricates a result. An unrecorded placeholder slot is reported as
``skipped: "unrecorded"`` rather than replayed, so the aggregate distinguishes
"recorded and rejected" from "not yet recorded". Synthetic-smoke fixtures are
usable for wiring but are flagged non-citable by the episode layer; only
``real-recorded`` episodes are evidence.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ..compiler import ExecutionPlan
from ..ledger import JsonlLedger
from .episode import EpisodeError, Episode, parse_episode, replay_episode
from .harness import RunResult
from .recompute import Recomputer
from .workspace import Workspace

STUDY_SCHEMA = "contractplane.dev/experimental/episode-study/v0"
CONDITIONS: tuple[str, ...] = ("correct", "overclaim", "borderline", "format-violation")
MODEL_SHORTS: tuple[str, ...] = ("opus", "sonnet", "haiku")
# The "count" family is implicit in filenames (episode-<model>-<condition>.json);
# the newer families carry a token (episode-<model>-<family>-<condition>.json).
FAMILIES: tuple[str, ...] = ("count", "aggregate", "filtercount")
_FAMILY_TOKENS: tuple[str, ...] = ("aggregate", "filtercount")
STUDY_NOTE = (
    "EXPERIMENTAL episode study across three mechanically recomputable task "
    "families (count, aggregate, filtercount). Rows derived from real replayed "
    "episodes only; placeholder slots are skipped, never fabricated. "
    "synthetic-smoke fixtures are wiring aids and MUST NOT be cited; only "
    "real-recorded episodes are evidence."
)


def _strip_suffix(stem: str, token: str) -> tuple[str, bool]:
    if stem == token:
        return "", True
    if stem.endswith(f"-{token}"):
        return stem[: -(len(token) + 1)], True
    return stem, False


def parse_filename(
    filename: str,
    conditions: tuple[str, ...] = CONDITIONS,
    families: tuple[str, ...] = _FAMILY_TOKENS,
) -> tuple[str, str, str | None]:
    """Split a fixture name into ``(model, family, condition)``.

    Filenames are ``episode-<model>[-<family>]-<condition>.json``. The ``count``
    family omits the family token. Conditions may contain hyphens
    (``format-violation``), so both condition and family are matched as known
    suffixes and the model is whatever remains.
    """
    stem = filename
    if stem.startswith("episode-"):
        stem = stem[len("episode-"):]
    if stem.endswith(".json"):
        stem = stem[: -len(".json")]

    condition: str | None = None
    for candidate in sorted(conditions, key=len, reverse=True):
        stripped, matched = _strip_suffix(stem, candidate)
        if matched:
            condition, stem = candidate, stripped
            break

    family = "count"
    for candidate in sorted(families, key=len, reverse=True):
        stripped, matched = _strip_suffix(stem, candidate)
        if matched:
            family, stem = candidate, stripped
            break

    return stem, family, condition


def _replay_row(
    episode: Episode,
    *,
    plans: dict[str, ExecutionPlan],
    pack_dir: Path,
    recomputer: Recomputer,
) -> dict[str, Any]:
    plan = plans.get(episode.flow)
    if plan is None:
        return {"error": f"episode names unknown flow {episode.flow!r}"}
    stage = plan.stages[0]
    evidence_id = stage.requires_evidence[0] if stage.requires_evidence else None
    expected = (
        recomputer.recompute(stage, evidence_id, episode.inputs) if evidence_id else None
    )
    field = next(iter(expected)) if expected else None
    artifact = episode.artifacts.get(evidence_id, {}) if evidence_id else {}
    claimed = artifact.get(field) if field else None
    truth = expected.get(field) if expected else None

    with tempfile.TemporaryDirectory(prefix="study-") as scratch:
        root = Path(scratch)
        report = replay_episode(
            episode,
            plan=plan,
            pack_dir=pack_dir,
            workspace=Workspace.create(root / "ws"),
            ledger=JsonlLedger(root / "ledger.jsonl"),
            execution_id="study",
            recomputer=recomputer,
        )

    verdict = report.verdicts[-1] if report.verdicts else None
    schema_gate = "fail" if (verdict and not verdict.accepted and verdict.method == "schema") else "pass"
    return {
        "checkedField": field,
        "dataset": episode.inputs.get("dataset") or episode.dataset,
        "claimed": claimed,
        "recomputed_truth": truth,
        "schema_gate": schema_gate,
        "verdict_method": verdict.method if verdict else None,
        "verdict": "accepted" if report.result is RunResult.SUCCEEDED else "rejected",
        "unit_advanced": report.result is RunResult.SUCCEEDED,
        "citable": episode.citable,
    }


def _status(entry: dict[str, Any]) -> str:
    if "skipped" in entry:
        return "skipped"
    if "error" in entry:
        return "error"
    return "accepted" if entry.get("verdict") == "accepted" else "rejected"


def _aggregate(
    episodes: list[dict[str, Any]],
    conditions: tuple[str, ...],
    families: tuple[str, ...],
) -> dict[str, Any]:
    table: dict[str, dict[str, dict[str, str]]] = {}
    counts = {"total": 0, "recorded": 0, "skipped": 0, "accepted": 0, "rejected": 0, "error": 0}
    by_condition = {c: {"accepted": 0, "rejected": 0, "skipped": 0, "error": 0} for c in conditions}
    by_family = {
        f: {"accepted": 0, "rejected": 0, "skipped": 0, "error": 0, "recorded": 0, "total": 0}
        for f in families
    }
    for entry in episodes:
        counts["total"] += 1
        model = entry.get("model") or "?"
        family = entry.get("family") or "?"
        condition = entry.get("condition") or "?"
        status = _status(entry)
        counts[status] = counts.get(status, 0) + 1
        if status not in ("skipped", "error"):
            counts["recorded"] += 1
        table.setdefault(family, {}).setdefault(model, {})[condition] = status
        if condition in by_condition:
            by_condition[condition][status] = by_condition[condition].get(status, 0) + 1
        if family in by_family:
            by_family[family][status] = by_family[family].get(status, 0) + 1
            by_family[family]["total"] += 1
            if status not in ("skipped", "error"):
                by_family[family]["recorded"] += 1
    return {
        "table": table,
        "counts": counts,
        "byCondition": by_condition,
        "byFamily": by_family,
    }


def run_study(
    study_dir: str | Path,
    *,
    pack_dir: Path,
    plans: dict[str, ExecutionPlan],
    recomputer: Recomputer,
    conditions: tuple[str, ...] = CONDITIONS,
    families: tuple[str, ...] = FAMILIES,
) -> dict[str, Any]:
    study_dir = Path(study_dir)
    episodes: list[dict[str, Any]] = []
    for path in sorted(study_dir.glob("episode-*.json")):
        model, family, condition = parse_filename(path.name, conditions)
        entry: dict[str, Any] = {
            "file": path.name,
            "model": model,
            "family": family,
            "condition": condition,
        }
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["error"] = f"unreadable episode: {exc}"
            episodes.append(entry)
            continue
        if raw.get("provenance") == "placeholder" or raw.get("status") == "unrecorded":
            entry["skipped"] = "unrecorded"
            episodes.append(entry)
            continue
        try:
            episode = parse_episode(raw, source=path.name)
            entry.update(_replay_row(episode, plans=plans, pack_dir=pack_dir, recomputer=recomputer))
        except EpisodeError as exc:
            entry["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - a replay fault is a study result, not a crash
            entry["error"] = f"replay failed: {exc}"
        episodes.append(entry)

    return {
        "schema": STUDY_SCHEMA,
        "note": STUDY_NOTE,
        "studyDir": str(study_dir),
        "conditions": list(conditions),
        "families": list(families),
        "models": sorted({e.get("model") or "?" for e in episodes}),
        "episodes": episodes,
        "aggregate": _aggregate(episodes, conditions, families),
    }


def write_study(report: dict[str, Any], out_path: str | Path) -> Path:
    target = Path(out_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
