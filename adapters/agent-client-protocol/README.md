# Agent Client Protocol adapter (EXPERIMENTAL)

A real, minimal [Agent Client Protocol](https://agentclientprotocol.com) (ACP)
integration that makes ContractPlane's substrate-neutrality a **measured** result
across two substrates: the in-process local-process subprocess adapter and this
ACP substrate. It is a research prototype layered on the experimental
governed-run slice; it is **not** part of the specified ContractPlane surface.

## What is here

- `acp_agent.mjs` — a real ACP **agent** built on the official
  `@zed-industries/agent-client-protocol` TypeScript SDK
  (`AgentSideConnection` over stdio, newline-delimited JSON-RPC 2.0). Its "work"
  is exactly the producer task the governed runs use: it shells out to the same
  Python worker (`examples/governed-run/workers/*.py`) or echoes a recorded
  claim, and writes the declared evidence artifact(s). Before doing any work it
  issues a real `session/request_permission` request.
- `package.json` / `node_modules/` — the installed SDK (v0.4.5).

The Python **client** half lives in
`src/contractplane/experimental/acp_adapter.py` (spawns this agent, drives
`initialize` -> `session/new` -> `session/prompt`, answers the permission request
from the compiled contract's authority decision) and
`src/contractplane/experimental/substrate.py` (the cross-substrate study).

## Setup

Requires Node (tested with v22.22.0). The SDK is already installed here; to
reinstall:

```
cd adapters/agent-client-protocol
npm install @zed-industries/agent-client-protocol
```

## Run the cross-substrate study

```
.venv/bin/python examples/governed-run/acp_substrate_study.py
```

This runs five governed conditions (correct, overclaim, borderline,
authority-denied, authority-granted) over both substrates and writes
`artifacts/acp_substrate_study.json`. The result to establish is that the
governed outcome is identical down each substrate column, and that the
authority-denial is enforced over real ACP `session/request_permission` messages
(the agent asks; the client answers deny-by-default; the agent does no work).

## The permission → authority mapping

The kernel's authority gate is deny-by-default. On the ACP substrate the agent
requests permission before its action; the client answers `allow`/`deny` using
the *same* `AuthorityGate.decide(stage)` the kernel uses. A denied external
action therefore never executes, and the denial travels as real ACP messages,
not an in-process short-circuit.

## What this adapter does NOT cover

It is a narrow, non-LLM agent: the "prompt" carries a JSON task envelope rather
than natural language, and it implements only the ACP subset the governed run
needs (initialize, session/new, session/prompt, session/request_permission,
session/update). It does not implement MCP servers, terminals, file-system
methods, session loading/modes, cancellation semantics, streaming model output,
or authentication — and it is not a conformance-tested ACP implementation.
