from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from contractplane.errors import LedgerError
from contractplane.ledger import JsonlLedger


def test_jsonl_ledger_is_append_only_and_sequence_checked(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    one = ledger.create_execution("run-1", {"planDigest": "abc"})
    two = ledger.create_execution("run-2", {"planDigest": "def"})
    three = ledger.append("run-1", "execution.started", {})
    assert [one["sequence"], two["sequence"], three["sequence"]] == [1, 2, 3]
    assert [event["type"] for event in ledger.read("run-1")] == [
        "execution.created",
        "execution.started",
    ]
    assert len(ledger.path.read_text(encoding="utf-8").splitlines()) == 3


def test_ledger_rejects_corruption_instead_of_guessing(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    ledger = JsonlLedger(path)
    ledger.create_execution("run", {})
    path.write_text(path.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")
    with pytest.raises(LedgerError, match="invalid JSON"):
        ledger.read()


def test_ledger_rejects_non_json_payload(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    with pytest.raises(LedgerError, match="not JSON-serializable"):
        ledger.append("run", "bad", {"value": object()})


def test_execution_creation_is_atomic_under_concurrency(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    workers = 8
    barrier = Barrier(workers)

    def create() -> str:
        barrier.wait()
        try:
            ledger.create_execution("same-run", {"planDigest": "abc"})
            return "created"
        except LedgerError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(lambda _: create(), range(workers)))
    assert outcomes.count("created") == 1
    assert outcomes.count("duplicate") == workers - 1
    events = ledger.read("same-run")
    assert len(events) == 1
    assert events[0]["schemaVersion"] == "contractplane.dev/kernel-state/v0alpha1"


def test_generic_append_cannot_bypass_atomic_creation(tmp_path: Path) -> None:
    ledger = JsonlLedger(tmp_path / "events.jsonl")
    with pytest.raises(LedgerError, match="create_execution"):
        ledger.append("run", "execution.created", {})
