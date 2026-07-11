from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TextIO

from .errors import LedgerError

LEDGER_SCHEMA_VERSION = "contractplane.dev/kernel-state/v0alpha1"


class JsonlLedger:
    """Append-only, process-safe-enough local event ledger.

    The ledger deliberately has no update or delete API. Sequence numbers are
    global to the file; ``executionId`` partitions multiple runs. Timestamps are
    omitted so identical transition sequences remain byte-for-byte reproducible.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    @contextmanager
    def _locked_file(self) -> Iterator[TextIO]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
            handle.seek(0)
            yield handle
        finally:
            try:
                handle.flush()
                os.fsync(handle.fileno())
            except OSError:
                pass
            handle.close()

    @staticmethod
    def _decode(handle: TextIO) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        expected_sequence = 1
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise LedgerError(f"blank line at ledger line {line_number}")
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"invalid JSON at ledger line {line_number}: {exc.msg}") from exc
            if not isinstance(event, dict):
                raise LedgerError(f"ledger line {line_number} must be a JSON object")
            if event.get("schemaVersion") != LEDGER_SCHEMA_VERSION:
                raise LedgerError(
                    f"unsupported ledger schema at line {line_number}: "
                    f"{event.get('schemaVersion')!r}"
                )
            if event.get("sequence") != expected_sequence:
                raise LedgerError(
                    f"non-contiguous ledger sequence at line {line_number}: "
                    f"expected {expected_sequence}, got {event.get('sequence')!r}"
                )
            if not isinstance(event.get("executionId"), str) or not event["executionId"]:
                raise LedgerError(f"missing executionId at ledger line {line_number}")
            if not isinstance(event.get("type"), str) or not event["type"]:
                raise LedgerError(f"missing event type at ledger line {line_number}")
            if not isinstance(event.get("payload"), dict):
                raise LedgerError(f"event payload must be an object at ledger line {line_number}")
            events.append(event)
            expected_sequence += 1
        return events

    def read(self, execution_id: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._locked_file() as handle:
            events = self._decode(handle)
        if execution_id is not None:
            return [event for event in events if event["executionId"] == execution_id]
        return events

    @staticmethod
    def _validate_append_args(
        execution_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        if not execution_id:
            raise LedgerError("execution_id must not be empty")
        if not event_type:
            raise LedgerError("event_type must not be empty")
        if not isinstance(payload, dict):
            raise LedgerError("payload must be a JSON object")
        try:
            json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise LedgerError(f"payload is not JSON-serializable: {exc}") from exc

    @staticmethod
    def _append_locked(
        handle: TextIO,
        events: list[dict[str, Any]],
        execution_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "schemaVersion": LEDGER_SCHEMA_VERSION,
            "sequence": len(events) + 1,
            "executionId": execution_id,
            "type": event_type,
            "payload": payload,
        }
        handle.seek(0, os.SEEK_END)
        handle.write(
            json.dumps(
                event,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
        return event

    def create_execution(self, execution_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Atomically reserve an execution id and append its creation event."""
        self._validate_append_args(execution_id, "execution.created", payload)
        with self._locked_file() as handle:
            events = self._decode(handle)
            if any(event["executionId"] == execution_id for event in events):
                raise LedgerError(f"execution {execution_id!r} already exists in {self.path}")
            return self._append_locked(
                handle, events, execution_id, "execution.created", payload
            )

    def append(self, execution_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_append_args(execution_id, event_type, payload)
        if event_type == "execution.created":
            raise LedgerError("use create_execution() for atomic execution creation")

        with self._locked_file() as handle:
            events = self._decode(handle)
            if not any(event["executionId"] == execution_id for event in events):
                raise LedgerError(
                    f"execution {execution_id!r} does not exist; call create_execution() first"
                )
            return self._append_locked(handle, events, execution_id, event_type, payload)

    def has_execution(self, execution_id: str) -> bool:
        return bool(self.read(execution_id))
