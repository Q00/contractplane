"""Executable local-process adapter.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

This is the first code in the repository that *consumes* a compiled capability
``binding`` instead of merely preserving it in the plan. Given a stage whose
binding names the ``local-process`` adapter, it dispatches the unit's work as a
real local subprocess: it writes a dispatch assignment (the validated input plus
harness-owned evidence write targets), runs the worker under the confined
workspace as its working directory, and reads back the worker's claimed outputs.

The adapter is deliberately *producer-side and untrusted*: the claimed outputs it
returns are gated downstream by the kernel's output schema, and the artifacts the
worker writes are checked downstream by an independent verifier. The adapter
never records evidence and never advances the kernel.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..compiler import CompiledStage
from .workspace import Workspace

ADAPTER_NAME = "local-process"
_DEFAULT_TIMEOUT_SECONDS = 30


class AdapterError(RuntimeError):
    """A local-process dispatch could not be carried out or produced no claim."""


@dataclass(frozen=True)
class DispatchResult:
    outputs: dict[str, Any]
    evidence_targets: dict[str, Path]
    returncode: int
    stderr: str


class LocalProcessAdapter:
    """Dispatch a stage's work as a bounded local subprocess."""

    def __init__(self, pack_dir: Path, *, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS):
        self._pack_dir = Path(pack_dir).expanduser().resolve()
        self._timeout_seconds = timeout_seconds

    def supports(self, stage: CompiledStage) -> bool:
        return bool(stage.binding) and stage.binding.get("adapter") == ADAPTER_NAME

    def _resolve_entry(self, stage: CompiledStage) -> Path:
        binding = stage.binding or {}
        config = binding.get("config") or {}
        entry = config.get("entry")
        if not entry:
            raise AdapterError(
                f"stage {stage.id!r} binding is missing config.entry for the local-process worker"
            )
        candidate = (self._pack_dir / entry).resolve()
        if self._pack_dir not in candidate.parents:
            raise AdapterError(
                f"worker entry {entry!r} for stage {stage.id!r} escapes the pack directory"
            )
        if not candidate.is_file():
            raise AdapterError(f"worker entry does not exist: {candidate}")
        return candidate

    def dispatch(
        self,
        stage: CompiledStage,
        inputs: dict[str, Any],
        workspace: Workspace,
    ) -> DispatchResult:
        if not self.supports(stage):
            raise AdapterError(
                f"adapter {ADAPTER_NAME!r} does not handle stage {stage.id!r}'s binding"
            )
        entry = self._resolve_entry(stage)
        evidence_targets = {
            evidence_id: workspace.evidence_path(stage.id, evidence_id)
            for evidence_id in stage.requires_evidence
        }
        assignment = {
            "stage": stage.id,
            "capability": stage.capability,
            "target": (stage.binding or {}).get("target"),
            "config": (stage.binding or {}).get("config") or {},
            "input": inputs,
            "evidenceTargets": {
                evidence_id: str(path) for evidence_id, path in evidence_targets.items()
            },
        }
        assignment_path = workspace.dispatch_path(stage.id)
        assignment_path.write_text(
            json.dumps(assignment, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

        completed = subprocess.run(
            [sys.executable, str(entry), str(assignment_path)],
            cwd=str(workspace.root),
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise AdapterError(
                f"worker for stage {stage.id!r} exited with code {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
        outputs = self._parse_outputs(stage, completed.stdout)
        return DispatchResult(
            outputs=outputs,
            evidence_targets=evidence_targets,
            returncode=completed.returncode,
            stderr=completed.stderr,
        )

    @staticmethod
    def _parse_outputs(stage: CompiledStage, stdout: str) -> dict[str, Any]:
        line = next(
            (raw for raw in reversed(stdout.splitlines()) if raw.strip()),
            None,
        )
        if line is None:
            raise AdapterError(f"worker for stage {stage.id!r} produced no claim on stdout")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"worker for stage {stage.id!r} emitted a non-JSON claim: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("outputs"), dict):
            raise AdapterError(
                f"worker for stage {stage.id!r} must emit an object with an 'outputs' object"
            )
        return payload["outputs"]
