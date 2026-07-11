"""LLM-producer episode harness.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

The default producer is a deterministic subprocess, which carries no agentic
content. This module lets a *real* LLM producer episode be recorded once and
replayed deterministically offline through the exact same kernel path
(dispatch -> claim -> recompute-verify -> verdict), so the governance loop is
exercised on genuine model output without a live API call in the test suite.

A *producer episode* is a JSON transcript with this shape::

    {
      "schema": "contractplane.dev/experimental/producer-episode/v0",
      "provenance": "real-recorded" | "synthetic-smoke",
      "adversarial": false,
      "model": "<model id or 'synthetic-smoke/none'>",
      "recordedAt": "<ISO-8601 or null>",
      "flow": "report",
      "input": { ...flow input... },
      "task": "<prompt given to the model>",
      "response": "<raw model response text>",
      "claim": {
        "outputs": { ...claimed capability outputs... },
        "artifact": { "<evidence-id>": { ...artifact the model produced... } }
      }
    }

Honesty rule (enforced structurally where possible):

* ``real-recorded`` transcripts must be actual recorded model outputs; they are
  the only provenance the paper may cite.
* ``synthetic-smoke`` transcripts are hand-authored fixtures used solely to
  exercise this runner; the paper must NOT cite them.
* An unrecorded placeholder slot (``provenance: "placeholder"`` or
  ``status: "unrecorded"``) is refused by :func:`load_episode`, so an empty slot
  can never be silently replayed as if it were evidence.
* ``adversarial`` marks a probe whose claim is expected to be rejected; it does
  not change replay, only documents intent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..compiler import CompiledStage, ExecutionPlan
from ..ledger import JsonlLedger
from .adapter import DispatchResult
from .authority import AuthorityGate
from .harness import GovernedRunner, RunReport
from .recompute import Recomputer
from .workspace import Workspace

EPISODE_SCHEMA = "contractplane.dev/experimental/producer-episode/v0"
CITABLE_PROVENANCE = frozenset({"real-recorded", "synthetic-smoke"})
PRODUCER_NAME = "episode-replay"


class EpisodeError(RuntimeError):
    """A producer episode transcript is malformed, a placeholder, or unusable."""


@dataclass(frozen=True)
class Episode:
    flow: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]
    provenance: str
    adversarial: bool
    model: str | None
    task: str | None
    response: str | None
    condition: str | None = None
    dataset: str | None = None

    @property
    def citable(self) -> bool:
        return self.provenance == "real-recorded"


def parse_episode(data: Any, *, source: str = "<memory>") -> Episode:
    if not isinstance(data, dict):
        raise EpisodeError(f"episode {source} must be a JSON object")
    if data.get("provenance") == "placeholder" or data.get("status") == "unrecorded":
        raise EpisodeError(
            f"episode {source} is an unrecorded placeholder slot; a real episode must be "
            "recorded before it can be replayed (see episodes/README.md)"
        )
    if data.get("schema") != EPISODE_SCHEMA:
        raise EpisodeError(
            f"episode {source} has schema {data.get('schema')!r}, expected {EPISODE_SCHEMA!r}"
        )
    provenance = data.get("provenance")
    if provenance not in CITABLE_PROVENANCE:
        raise EpisodeError(
            f"episode {source} provenance {provenance!r} must be one of {sorted(CITABLE_PROVENANCE)}"
        )
    flow = data.get("flow")
    if not isinstance(flow, str) or not flow:
        raise EpisodeError(f"episode {source} must name a flow")
    inputs = data.get("input")
    if not isinstance(inputs, dict):
        raise EpisodeError(f"episode {source} must carry an 'input' object")
    claim = data.get("claim")
    if not isinstance(claim, dict):
        raise EpisodeError(f"episode {source} must carry a 'claim' object")
    outputs = claim.get("outputs")
    if not isinstance(outputs, dict):
        raise EpisodeError(f"episode {source} claim.outputs must be an object")
    artifacts = claim.get("artifact", {})
    if not isinstance(artifacts, dict) or not all(
        isinstance(value, dict) for value in artifacts.values()
    ):
        raise EpisodeError(f"episode {source} claim.artifact must map evidence ids to objects")
    return Episode(
        flow=flow,
        inputs=inputs,
        outputs=outputs,
        artifacts=artifacts,
        provenance=provenance,
        adversarial=bool(data.get("adversarial", False)),
        model=data.get("model"),
        task=data.get("task"),
        response=data.get("response"),
        condition=data.get("condition"),
        dataset=data.get("dataset"),
    )


def load_episode(path: str | Path) -> Episode:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EpisodeError(f"episode file does not exist: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EpisodeError(f"episode {source} is not valid JSON: {exc.msg}") from exc
    return parse_episode(data, source=str(source))


class EpisodeProducer:
    """Replay a recorded transcript as a governed producer.

    It writes the model's recorded artifact(s) to the harness-owned evidence
    address and returns the model's recorded claim as outputs. It does no
    verification of its own; the independent verifier still recomputes ground
    truth and decides advancement, so an adversarial episode is rejected exactly
    as a live overclaiming model would be.
    """

    def __init__(self, episode: Episode):
        self._episode = episode

    def supports(self, stage: CompiledStage) -> bool:
        return True

    def dispatch(
        self, stage: CompiledStage, inputs: dict[str, Any], workspace: Workspace
    ) -> DispatchResult:
        evidence_targets: dict[str, Path] = {}
        for evidence_id in stage.requires_evidence:
            if evidence_id not in self._episode.artifacts:
                raise EpisodeError(
                    f"episode has no recorded artifact for evidence {evidence_id!r} "
                    f"required by stage {stage.id!r}"
                )
            path = workspace.evidence_path(stage.id, evidence_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._episode.artifacts[evidence_id], ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            evidence_targets[evidence_id] = path
        return DispatchResult(
            outputs=self._episode.outputs,
            evidence_targets=evidence_targets,
            returncode=0,
            stderr="",
        )


def replay_episode(
    episode: Episode,
    *,
    plan: ExecutionPlan,
    pack_dir: Path,
    workspace: Workspace,
    ledger: JsonlLedger,
    execution_id: str,
    recomputer: Recomputer | None = None,
    authority: AuthorityGate | None = None,
) -> RunReport:
    """Drive a recorded episode through the standard governed run path."""
    runner = GovernedRunner(
        plan,
        pack_dir=pack_dir,
        workspace=workspace,
        ledger=ledger,
        authority=authority,
        recomputer=recomputer,
        producer=EpisodeProducer(episode),
    )
    return runner.run(episode.inputs, execution_id=execution_id)
