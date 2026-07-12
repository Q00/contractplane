"""Tests for commit-reveal sealing of study ground truths (EXPERIMENTAL).

Covers the sealing primitives (canonicalization, round-trip verification, tamper
detection), the committed Track A/B seal's blindness (no truth values in the
committed artifact), and — when the local preimage is present — that the committed
seal actually verifies. The preimage is gitignored until reveal, so that last check
skips honestly on checkouts that do not have it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from contractplane.experimental import build_seal, commitment_of, verify_seal
from contractplane.experimental.sealing import canonical_payload

ROOT = Path(__file__).resolve().parents[1]
SEALS_DIR = ROOT / "examples" / "governed-run" / "seals"
COMMITTED_SEAL = SEALS_DIR / "seal-2026-07-12-trackAB.json"
LOCAL_PREIMAGE = SEALS_DIR / "PREIMAGE-seal-2026-07-12-trackAB.local.json"

TRUTHS = {"demo-a:count": 42, "demo-b:sum": 1234}


def test_canonical_payload_is_key_order_independent() -> None:
    a = canonical_payload({"x": 1, "y": 2}, "s")
    b = canonical_payload({"y": 2, "x": 1}, "s")
    assert a == b


def test_build_and_verify_round_trip() -> None:
    seal, preimage = build_seal(TRUTHS, sealed_at="2026-07-12T00:00:00Z", scope="test")
    result = verify_seal(seal, preimage)
    assert result["matches"] is True
    assert result["committed"] == result["recomputed"] == seal["commitment"]


def test_tampered_preimage_is_detected() -> None:
    seal, preimage = build_seal(TRUTHS, sealed_at="2026-07-12T00:00:00Z", scope="test")
    tampered = json.loads(json.dumps(preimage))
    tampered["truths"]["demo-a:count"] = 43
    result = verify_seal(seal, tampered)
    assert result["matches"] is False
    assert "MISMATCH" in result["verdict"]


def test_salt_changes_commitment_preventing_dictionary_attack() -> None:
    assert commitment_of(TRUTHS, "salt-1") != commitment_of(TRUTHS, "salt-2")


def test_seal_carries_no_truth_values() -> None:
    seal, _ = build_seal(TRUTHS, sealed_at="2026-07-12T00:00:00Z", scope="test")
    assert "truths" not in seal
    blob = json.dumps(seal)
    assert "42" not in blob.replace(seal["commitment"], "")
    assert seal["truthKeys"] == sorted(TRUTHS)


def test_committed_trackab_seal_is_blind_and_well_formed() -> None:
    seal = json.loads(COMMITTED_SEAL.read_text(encoding="utf-8"))
    assert seal["schema"] == "producer-study-seal/v0"
    assert re.fullmatch(r"[0-9a-f]{64}", seal["commitment"])
    assert "truths" not in seal
    # Every hard dataset in scope is sealed for both count and sum.
    for name in ("f", "g", "g2", "g3", "h", "h2", "h3"):
        assert f"hard-count-{name}:count" in seal["truthKeys"]
        assert f"hard-count-{name}:sum" in seal["truthKeys"]


@pytest.mark.skipif(
    not LOCAL_PREIMAGE.is_file(),
    reason="preimage is local-only until reveal; verification runs where it exists",
)
def test_committed_trackab_seal_verifies_against_local_preimage() -> None:
    seal = json.loads(COMMITTED_SEAL.read_text(encoding="utf-8"))
    preimage = json.loads(LOCAL_PREIMAGE.read_text(encoding="utf-8"))
    assert verify_seal(seal, preimage)["matches"] is True
