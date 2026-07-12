"""Commit-reveal sealing of study ground truths (EXPERIMENTAL).

Blinding in the natural-error studies is procedural: recorders are never told the
truths. A commit-reveal seal makes that blinding *auditable to third parties*:

1. **Commit** (before any recording): the orchestrator writes a preimage file
   ``{"truths": {...}, "salt": "<random hex>"}`` kept OUT of version control, and
   commits only its SHA-256 over a canonical JSON encoding to the repository.
2. **Record**: producer/judge episodes are harvested while the preimage stays local.
3. **Reveal** (after recording completes): the preimage file is published; anyone
   recomputes the hash and checks it against the committed seal, proving the truths
   were fixed before the models ran — datasets were not tuned after seeing outputs.

The salt prevents dictionary attacks on the (small) truth space; without it, a
seal over ``{"hard-count-f": 273}`` could be brute-forced from the commitment.

Nothing here reads episodes or datasets: truths are passed in by the orchestrator
(typically computed via ``HardCountRecomputer``/``HardSumRecomputer``), so this
module cannot leak what it was never given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

SEAL_SCHEMA = "producer-study-seal/v0"
SEAL_ALGORITHM = "sha256-over-canonical-json"


def canonical_payload(truths: dict[str, Any], salt: str) -> bytes:
    """Deterministic byte encoding of the preimage: sorted keys, no whitespace."""
    return json.dumps(
        {"salt": salt, "truths": truths}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def commitment_of(truths: dict[str, Any], salt: str) -> str:
    return hashlib.sha256(canonical_payload(truths, salt)).hexdigest()


def build_seal(
    truths: dict[str, Any],
    *,
    sealed_at: str,
    scope: str,
    salt: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(seal, preimage)``.

    The *seal* is safe to commit: it carries only the commitment hash and metadata,
    never a truth value. The *preimage* must stay out of version control until the
    reveal step.
    """
    salt = salt or secrets.token_hex(16)
    seal = {
        "schema": SEAL_SCHEMA,
        "algorithm": SEAL_ALGORITHM,
        "sealedAt": sealed_at,
        "scope": scope,
        "truthKeys": sorted(truths),
        "commitment": commitment_of(truths, salt),
        "revealPolicy": (
            "The preimage file (truths + salt) is published only after every "
            "recording in scope is complete; recomputing the commitment over the "
            "canonical JSON encoding must reproduce the committed hash."
        ),
    }
    preimage = {"schema": SEAL_SCHEMA + "-preimage", "salt": salt, "truths": truths}
    return seal, preimage


def verify_seal(seal: dict[str, Any], preimage: dict[str, Any]) -> dict[str, Any]:
    """Recompute the commitment from a preimage and compare against the seal."""
    recomputed = commitment_of(preimage.get("truths", {}), preimage.get("salt", ""))
    committed = seal.get("commitment")
    matches = recomputed == committed
    return {
        "matches": matches,
        "committed": committed,
        "recomputed": recomputed,
        "truthKeys": sorted(preimage.get("truths", {})),
        "verdict": "seal verified: truths were fixed before recording"
        if matches
        else "SEAL MISMATCH: preimage does not reproduce the committed hash",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a commit-reveal study seal.")
    parser.add_argument("seal", help="path to the committed seal JSON")
    parser.add_argument("preimage", help="path to the (revealed) preimage JSON")
    args = parser.parse_args(argv)
    result = verify_seal(_read_json(Path(args.seal)), _read_json(Path(args.preimage)))
    print(json.dumps(result, indent=2))
    return 0 if result["matches"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
