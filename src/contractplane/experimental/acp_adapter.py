"""Agent Client Protocol (ACP) client adapter — the second substrate.

EXPERIMENTAL — see :mod:`contractplane.experimental`.

This is a real ACP *client*: it spawns the Node ACP *agent*
(``adapters/agent-client-protocol/acp_agent.mjs``, built on the official
``@zed-industries/agent-client-protocol`` SDK) as a subprocess and drives a real
ACP session over newline-delimited JSON-RPC 2.0 on stdio: ``initialize`` ->
``session/new`` -> ``session/prompt``, handling the agent's
``session/request_permission`` request and ``session/update`` notifications.

The whole point is substrate-neutrality: the same producer task the
local-process substrate runs is executed here over ACP instead, and ACP's
permission-request primitive is answered from the compiled contract's authority
decision (deny-by-default). The producer's ACP-returned claim then flows through
the SAME kernel claim -> recompute-verify -> verdict path.

There is no Python ACP SDK, so the client half of the wire protocol is a minimal
hand-written JSON-RPC peer; the AGENT uses the official SDK. This is labelled
honestly and only implements the subset the governed run needs.
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parents[3]
ACP_DIR = _REPO_ROOT / "adapters" / "agent-client-protocol"
AGENT_SCRIPT = ACP_DIR / "acp_agent.mjs"
_NVM_NODE = Path.home() / ".nvm" / "versions" / "node" / "v22.22.0" / "bin" / "node"
_DEFAULT_TIMEOUT = 30.0


class ACPError(RuntimeError):
    """An ACP session failed at the transport or agent level."""


class ACPPermissionDenied(RuntimeError):
    """The ACP permission request was denied by contract authority over ACP."""


def node_executable() -> str | None:
    found = shutil.which("node")
    if found:
        return found
    if _NVM_NODE.is_file():
        return str(_NVM_NODE)
    return None


def acp_available() -> tuple[bool, str]:
    """Report whether a real ACP session can run, with a reason if not."""
    node = node_executable()
    if node is None:
        return False, "node executable not found on PATH or in ~/.nvm"
    if not AGENT_SCRIPT.is_file():
        return False, f"ACP agent script missing: {AGENT_SCRIPT}"
    if not (ACP_DIR / "node_modules" / "@zed-industries" / "agent-client-protocol").is_dir():
        return False, "ACP SDK not installed (run npm install in adapters/agent-client-protocol)"
    return True, "ok"


@dataclass
class ACPResult:
    allowed: bool
    permission_requested: bool
    stop_reason: str
    outputs: dict[str, Any] | None
    session_id: str
    protocol_version: int
    agent_messages: list[dict[str, Any]] = field(default_factory=list)


class _ACPSession:
    """A minimal JSON-RPC 2.0 peer speaking ACP to the Node agent subprocess."""

    def __init__(self, node: str, cwd: Path, timeout: float):
        self._timeout = timeout
        self._next_id = 0
        self._stderr: list[str] = []
        self._proc = subprocess.Popen(
            [node, str(AGENT_SCRIPT)],
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self._stderr.append(line.rstrip("\n"))

    def __enter__(self) -> "_ACPSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def _diagnostics(self) -> str:
        return "; ".join(self._stderr[-5:]) if self._stderr else "(no stderr)"

    def _write(self, message: dict[str, Any]) -> None:
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ACPError(f"ACP agent stdin closed: {exc}; stderr: {self._diagnostics()}") from exc

    def _readline(self, deadline: float) -> str:
        assert self._proc.stdout is not None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ACPError(f"ACP session timed out; stderr: {self._diagnostics()}")
            ready, _, _ = select.select([self._proc.stdout], [], [], remaining)
            if not ready:
                continue
            line = self._proc.stdout.readline()
            if line == "":
                raise ACPError(
                    f"ACP agent closed stdout unexpectedly; stderr: {self._diagnostics()}"
                )
            if line.strip():
                return line

    def request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        on_request: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        on_notification: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self._timeout
        while True:
            message = json.loads(self._readline(deadline))
            if "id" in message and ("result" in message or "error" in message):
                if message["id"] != request_id:
                    continue
                if "error" in message:
                    raise ACPError(f"ACP {method} error: {message['error']}")
                return message["result"]
            if "method" in message and "id" in message:
                # Inbound request from the agent (e.g. session/request_permission).
                handler_result: dict[str, Any] = {}
                if on_request is not None:
                    handler_result = on_request(message["method"], message.get("params") or {})
                self._write({"jsonrpc": "2.0", "id": message["id"], "result": handler_result})
            elif "method" in message:
                if on_notification is not None:
                    on_notification(message["method"], message.get("params") or {})

    def initialize(self) -> int:
        result = self.request(
            "initialize",
            {"protocolVersion": 1, "clientCapabilities": {}},
        )
        return int(result.get("protocolVersion", 1))

    def new_session(self, cwd: Path) -> str:
        result = self.request("session/new", {"cwd": str(cwd), "mcpServers": []})
        return result["sessionId"]


def run_acp_task(
    task: dict[str, Any],
    *,
    allow: bool,
    cwd: Path,
    node: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> ACPResult:
    """Run one producer task over a real ACP session.

    ``allow`` is the contract authority decision; it is delivered to the agent as
    a real ACP ``session/request_permission`` response. On allow the agent
    produces the claim (worker or echo) and returns its outputs; on deny the
    agent performs no work.
    """
    node = node or node_executable()
    if node is None:
        raise ACPError("node executable not available")

    permission_requested = {"value": False}
    agent_messages: list[dict[str, Any]] = []

    def on_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "session/request_permission":
            permission_requested["value"] = True
            option = "allow" if allow else "deny"
            return {"outcome": {"outcome": "selected", "optionId": option}}
        return {}

    def on_notification(method: str, params: dict[str, Any]) -> None:
        if method == "session/update":
            update = params.get("update") or {}
            if update.get("sessionUpdate") == "agent_message_chunk":
                content = update.get("content") or {}
                if content.get("type") == "text":
                    try:
                        agent_messages.append(json.loads(content["text"]))
                    except (ValueError, KeyError):
                        pass

    with _ACPSession(node, cwd, timeout) as session:
        protocol_version = session.initialize()
        session_id = session.new_session(cwd)
        prompt_params = {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": json.dumps(task)}],
        }
        response = session.request(
            "session/prompt",
            prompt_params,
            on_request=on_request,
            on_notification=on_notification,
        )
        stop_reason = response.get("stopReason", "")

    outputs = None
    for message in agent_messages:
        if isinstance(message, dict) and isinstance(message.get("outputs"), dict):
            outputs = message["outputs"]
    if allow and stop_reason == "refusal":
        detail = next((m for m in agent_messages if "acpError" in m), {})
        raise ACPError(f"ACP agent refused an allowed task: {detail.get('acpError', 'unknown')}")

    return ACPResult(
        allowed=allow,
        permission_requested=permission_requested["value"],
        stop_reason=stop_reason,
        outputs=outputs,
        session_id=session_id,
        protocol_version=protocol_version,
        agent_messages=agent_messages,
    )
