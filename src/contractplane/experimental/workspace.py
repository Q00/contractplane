"""Harness-owned artifact addressing and workspace confinement.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

This module is the single source of truth for *where* a governed run's evidence
artifacts live. Both the producer side (the adapter, which tells a worker where
to write) and the independent verifier (which re-reads the same location) derive
paths from :func:`evidence_artifact_path`. A producer therefore cannot point the
verifier at a doctored file: the verifier computes the canonical address itself
and only trusts what it finds there, inside the confined workspace root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def evidence_artifact_path(workspace_root: Path, stage_id: str, evidence_id: str) -> Path:
    """Return the canonical, workspace-confined path for one evidence artifact.

    The naming convention is owned by the harness, not by any producer, so the
    address is identical whether the adapter is assigning a write target or the
    verifier is re-reading ground truth.
    """
    return workspace_root / "evidence" / f"{stage_id}.{evidence_id}.json"


@dataclass(frozen=True)
class Workspace:
    """A bounded local directory that confines all governed side effects."""

    root: Path

    @classmethod
    def create(cls, root: Path) -> "Workspace":
        resolved = Path(root).expanduser().resolve()
        (resolved / "evidence").mkdir(parents=True, exist_ok=True)
        (resolved / "_dispatch").mkdir(parents=True, exist_ok=True)
        return cls(resolved)

    def contains(self, candidate: Path) -> bool:
        """Report whether ``candidate`` resolves to a path inside this workspace.

        This is the real confinement check: it resolves symlinks and ``..``
        components before comparing, so a producer cannot escape the workspace by
        handing back a traversal path.
        """
        try:
            resolved = Path(candidate).expanduser().resolve()
        except (OSError, RuntimeError):
            return False
        return resolved == self.root or self.root in resolved.parents

    def evidence_path(self, stage_id: str, evidence_id: str) -> Path:
        return evidence_artifact_path(self.root, stage_id, evidence_id)

    def dispatch_path(self, stage_id: str) -> Path:
        return self.root / "_dispatch" / f"{stage_id}.json"
