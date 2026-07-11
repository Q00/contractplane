"""Multi-step agentic claim-chain study.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

The prior studies measure single-step claims. This module measures the last
unaddressed axis: a *multi-step agentic chain* where later work consumes the
model's own earlier self-reports. One model works three steps in sequence,
tool-less:

1. ``count`` — count the records of dataset X.
2. ``sum`` — sum the value field of dataset Y.
3. ``derive`` — report ``count + sum``, computed from its OWN step 1 and step 2
   claims (that is the agentic dependency: the derived answer inherits earlier
   self-reports, right or wrong).

Every step produces its own claim through the same governed kernel path, and the
recomputation verifier checks each step independently against ground truth
recomputed from the raw datasets (:class:`HardCountRecomputer`,
:class:`HardSumRecomputer`, and :class:`ChainDerivedRecomputer` for the end-to-end
derived quantity). Because the kernel gates each step before the next runs, a
wrong early step halts the chain at that step — the derived output is never
produced or accepted. That is *blast-radius containment*: the governed property
that plain agent frameworks, which let an early hallucinated number flow into the
final answer, lack.

The runner scores each step ``{claimed, truth, error, verdict}`` and the
chain-level questions: did an early error propagate into the model's derived final
claim (what an ungoverned chain would accept), and did per-step gating contain the
chain at the first wrong step (what the governed path does instead).

Honesty protocol mirrors the other studies: only ``real-recorded`` chain episodes
are evidence; unrecorded placeholder slots refuse replay and are never fabricated;
``synthetic-smoke`` fixtures are wiring aids flagged non-citable.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..compiler import ExecutionPlan, compile_plan
from ..ledger import JsonlLedger
from ..loader import load_domain_pack
from .adapter import DispatchResult
from .harness import GovernedRunner, RunResult
from .natural_study import HardCountRecomputer, HardSumRecomputer
from .recompute import ChainRecomputer
from .workspace import Workspace

CHAIN_STUDY_SCHEMA = "contractplane.dev/experimental/chain-study/v0"
CHAIN_EPISODE_KIND = "chain-episode"
BASE_EPISODE_SCHEMA = "contractplane.dev/experimental/producer-episode/v0"
CITABLE_PROVENANCE = frozenset({"real-recorded", "synthetic-smoke"})

CHAIN_STEPS: tuple[str, ...] = ("count", "sum", "derive")
STEP_EVIDENCE = {
    "count": "chain-count-artifact",
    "sum": "chain-sum-artifact",
    "derive": "chain-derived-artifact",
}
STEP_FIELD = {"count": "rows", "sum": "total", "derive": "derived"}


class ChainEpisodeError(RuntimeError):
    """A chain episode transcript is malformed, a placeholder, or unusable."""


class ChainDerivedRecomputer:
    """Recompute the end-to-end derived total ``count(X) + sum(Y)`` from raw data.

    This is the ground truth for the derived step: it is computed from the two
    caller-owned datasets, never from the model's earlier claims, so a derived
    answer that inherited an earlier self-report error is rejected here.
    """

    def __init__(
        self,
        datasets_dir: Path,
        *,
        evidence_ids: frozenset[str] = frozenset({"chain-derived-artifact"}),
        expect_field: str = "derived",
    ) -> None:
        self.datasets_dir = Path(datasets_dir)
        self.evidence_ids = evidence_ids
        self.expect_field = expect_field
        self._count = HardCountRecomputer(datasets_dir)
        self._sum = HardSumRecomputer(datasets_dir)

    def recompute(self, stage: Any, evidence_id: str, inputs: dict[str, Any]) -> dict[str, Any] | None:
        if evidence_id not in self.evidence_ids:
            return None
        dataset_x = (inputs or {}).get("datasetX")
        dataset_y = (inputs or {}).get("datasetY")
        if not isinstance(dataset_x, str) or not isinstance(dataset_y, str):
            return None
        source_x = self.datasets_dir / f"{dataset_x}.json"
        source_y = self.datasets_dir / f"{dataset_y}.json"
        if not source_x.is_file() or not source_y.is_file():
            return None
        count = self._count.count_records(json.loads(source_x.read_text(encoding="utf-8")))
        total = self._sum.sum_records(json.loads(source_y.read_text(encoding="utf-8")))
        if count is None or total is None:
            return None
        return {self.expect_field: count + total}


def chain_recomputer(datasets_dir: Path) -> ChainRecomputer:
    return ChainRecomputer(
        [
            HardCountRecomputer(
                datasets_dir,
                evidence_ids=frozenset({"chain-count-artifact"}),
                dataset_key="datasetX",
                expect_field="rows",
            ),
            HardSumRecomputer(
                datasets_dir,
                evidence_ids=frozenset({"chain-sum-artifact"}),
                dataset_key="datasetY",
                expect_field="total",
            ),
            ChainDerivedRecomputer(datasets_dir),
        ]
    )


@dataclass(frozen=True)
class ChainStep:
    name: str
    evidence: str
    outputs: dict[str, Any]
    artifact: dict[str, Any]
    task: str | None
    response: str | None


@dataclass(frozen=True)
class ChainEpisode:
    inputs: dict[str, Any]
    provenance: str
    model: str | None
    steps: tuple[ChainStep, ...]

    @property
    def citable(self) -> bool:
        return self.provenance == "real-recorded"

    def step(self, name: str) -> ChainStep:
        for step in self.steps:
            if step.name == name:
                return step
        raise ChainEpisodeError(f"chain episode has no {name!r} step")


def parse_chain_episode(data: Any, *, source: str = "<memory>") -> ChainEpisode:
    if not isinstance(data, dict):
        raise ChainEpisodeError(f"chain episode {source} must be a JSON object")
    if data.get("provenance") == "placeholder" or data.get("status") == "unrecorded":
        raise ChainEpisodeError(
            f"chain episode {source} is an unrecorded placeholder slot; a real chain must be "
            "recorded before it can be replayed (see episodes/study-chain/README.md)"
        )
    if data.get("kind") != CHAIN_EPISODE_KIND:
        raise ChainEpisodeError(f"chain episode {source} must set kind={CHAIN_EPISODE_KIND!r}")
    provenance = data.get("provenance")
    if provenance not in CITABLE_PROVENANCE:
        raise ChainEpisodeError(
            f"chain episode {source} provenance {provenance!r} must be one of {sorted(CITABLE_PROVENANCE)}"
        )
    if data.get("flow") != "chain":
        raise ChainEpisodeError(f"chain episode {source} must name flow 'chain'")
    inputs = data.get("input")
    if not isinstance(inputs, dict) or "datasetX" not in inputs or "datasetY" not in inputs:
        raise ChainEpisodeError(f"chain episode {source} input must carry datasetX and datasetY")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) != len(CHAIN_STEPS):
        raise ChainEpisodeError(f"chain episode {source} must carry exactly {len(CHAIN_STEPS)} steps")

    by_name: dict[str, ChainStep] = {}
    for raw in raw_steps:
        if not isinstance(raw, dict):
            raise ChainEpisodeError(f"chain episode {source} step must be an object")
        name = raw.get("step")
        if name not in CHAIN_STEPS:
            raise ChainEpisodeError(f"chain episode {source} has unknown step {name!r}")
        evidence = raw.get("evidence")
        if evidence != STEP_EVIDENCE[name]:
            raise ChainEpisodeError(f"chain episode {source} step {name!r} evidence must be {STEP_EVIDENCE[name]!r}")
        claim = raw.get("claim") or {}
        outputs = claim.get("outputs")
        artifact = claim.get("artifact") or {}
        if not isinstance(outputs, dict):
            raise ChainEpisodeError(f"chain episode {source} step {name!r} claim.outputs must be an object")
        if not isinstance(artifact.get(evidence), dict):
            raise ChainEpisodeError(
                f"chain episode {source} step {name!r} must record an artifact for {evidence!r}"
            )
        by_name[name] = ChainStep(name, evidence, outputs, artifact, raw.get("task"), raw.get("response"))

    steps = tuple(by_name[name] for name in CHAIN_STEPS)
    return ChainEpisode(inputs=inputs, provenance=provenance, model=data.get("model"), steps=steps)


def load_chain_episode(path: str | Path) -> ChainEpisode:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ChainEpisodeError(f"chain episode file does not exist: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChainEpisodeError(f"chain episode {source} is not valid JSON: {exc.msg}") from exc
    return parse_chain_episode(data, source=str(source))


class ChainEpisodeProducer:
    """Replay a recorded chain: per governed stage, write that step's artifact."""

    def __init__(self, episode: ChainEpisode):
        self._by_evidence = {step.evidence: step for step in episode.steps}

    def supports(self, stage: Any) -> bool:
        return True

    def dispatch(self, stage: Any, inputs: dict[str, Any], workspace: Workspace) -> DispatchResult:
        evidence_id = stage.requires_evidence[0]
        step = self._by_evidence.get(evidence_id)
        if step is None:
            raise ChainEpisodeError(f"chain episode has no step for evidence {evidence_id!r}")
        path = workspace.evidence_path(stage.id, evidence_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(step.artifact[evidence_id], ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return DispatchResult(outputs=step.outputs, evidence_targets={evidence_id: path}, returncode=0, stderr="")


def score_chain(
    episode: ChainEpisode,
    *,
    plan: ExecutionPlan,
    pack_dir: Path,
    datasets_dir: Path,
    workspace: Workspace,
    ledger: JsonlLedger,
    execution_id: str,
) -> dict[str, Any]:
    recomputer = chain_recomputer(datasets_dir)
    runner = GovernedRunner(
        plan,
        pack_dir=pack_dir,
        workspace=workspace,
        ledger=ledger,
        producer=ChainEpisodeProducer(episode),
        recomputer=recomputer,
    )
    report = runner.run(episode.inputs, execution_id=execution_id)
    verdict_by_evidence = {v.evidence_id: v for v in report.verdicts}

    steps_out: list[dict[str, Any]] = []
    claimed: dict[str, Any] = {}
    truth: dict[str, Any] = {}
    for name in CHAIN_STEPS:
        step = episode.step(name)
        field = STEP_FIELD[name]
        step_claim = step.artifact[step.evidence].get(field)
        stage = plan.stage_map[name]
        expected = recomputer.recompute(stage, step.evidence, episode.inputs)
        step_truth = expected.get(field) if expected else None
        verdict = verdict_by_evidence.get(step.evidence)
        verdict_str = ("accepted" if verdict.accepted else "rejected") if verdict is not None else "not-reached"
        claimed[name] = step_claim
        truth[name] = step_truth
        steps_out.append(
            {
                "step": name,
                "evidence": step.evidence,
                "field": field,
                "claimed": step_claim,
                "truth": step_truth,
                "error": step_claim != step_truth,
                "verdict": verdict_str,
            }
        )

    first_error_step = next((s["step"] for s in steps_out if s["error"]), None)
    early_error = first_error_step in ("count", "sum")
    derive_verdict = next(s["verdict"] for s in steps_out if s["step"] == "derive")
    derived_from_own = (
        (claimed["count"] or 0) + (claimed["sum"] or 0)
        if claimed["count"] is not None and claimed["sum"] is not None
        else None
    )
    propagated = bool(early_error and claimed["derive"] is not None and claimed["derive"] != truth["derive"])
    contained = bool(early_error and derive_verdict != "accepted")

    return {
        "model": episode.model,
        "provenance": episode.provenance,
        "citable": episode.citable,
        "datasetX": episode.inputs.get("datasetX"),
        "datasetY": episode.inputs.get("datasetY"),
        "steps": steps_out,
        "governedResult": _result_str(report.result),
        "haltedAtStep": report.rejected_stage,
        "firstErrorStep": first_error_step,
        "derivedClaim": claimed["derive"],
        "derivedTruth": truth["derive"],
        "derivedFromOwnArithmetic": derived_from_own,
        "derivedMatchesOwnArithmetic": claimed["derive"] == derived_from_own,
        "errorPropagatedIntoFinalClaim": propagated,
        "blastRadiusContained": contained,
    }


def _result_str(result: RunResult) -> str:
    return {RunResult.SUCCEEDED: "succeeded", RunResult.REJECTED: "rejected", RunResult.DENIED: "denied"}[result]


def run_chain_study(study_dir: str | Path, *, pack_dir: Path, datasets_dir: Path) -> dict[str, Any]:
    study_dir = Path(study_dir)
    pack = load_domain_pack(pack_dir / "domainpack.yaml")
    plan = compile_plan(pack, entrypoint_id="chain")

    episodes: list[dict[str, Any]] = []
    for path in sorted(study_dir.glob("episode-*.json")):
        entry: dict[str, Any] = {"file": path.name}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["error"] = f"unreadable chain episode: {exc}"
            episodes.append(entry)
            continue
        if raw.get("provenance") == "placeholder" or raw.get("status") == "unrecorded":
            entry["skipped"] = "unrecorded"
            entry["model"] = raw.get("model")
            episodes.append(entry)
            continue
        try:
            episode = parse_chain_episode(raw, source=path.name)
            with tempfile.TemporaryDirectory(prefix="chain-") as scratch:
                root = Path(scratch)
                entry.update(
                    score_chain(
                        episode,
                        plan=plan,
                        pack_dir=pack_dir,
                        datasets_dir=datasets_dir,
                        workspace=Workspace.create(root / "ws"),
                        ledger=JsonlLedger(root / "ledger.jsonl"),
                        execution_id="chain",
                    )
                )
        except ChainEpisodeError as exc:
            entry["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - a replay fault is a study result, not a crash
            entry["error"] = f"replay failed: {exc}"
        episodes.append(entry)

    scored = [e for e in episodes if "steps" in e]
    early_error_chains = [e for e in scored if e["firstErrorStep"] in ("count", "sum")]
    summary = {
        "total": len(episodes),
        "recorded": len(scored),
        "skipped": sum(1 for e in episodes if "skipped" in e),
        "error": sum(1 for e in episodes if "error" in e),
        "chainsFullyAccepted": sum(1 for e in scored if e["governedResult"] == "succeeded"),
        "chainsRejected": sum(1 for e in scored if e["governedResult"] == "rejected"),
        "earlyErrorChains": len(early_error_chains),
        "earlyErrorsPropagatedInClaim": sum(1 for e in early_error_chains if e["errorPropagatedIntoFinalClaim"]),
        "earlyErrorsContainedByGovernance": sum(1 for e in early_error_chains if e["blastRadiusContained"]),
    }
    return {
        "schema": CHAIN_STUDY_SCHEMA,
        "note": (
            "EXPERIMENTAL multi-step agentic claim-chain study. Each of the three steps is "
            "independently recompute-verified through the same kernel; a wrong early step halts "
            "the chain (blast-radius containment). Rows derive from real replayed chain episodes "
            "only; placeholders are skipped, never fabricated; synthetic-smoke fixtures are not citable."
        ),
        "studyDir": str(study_dir),
        "steps": list(CHAIN_STEPS),
        "episodes": episodes,
        "summary": summary,
    }


def write_chain_study(report: dict[str, Any], out_path: str | Path) -> Path:
    target = Path(out_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
