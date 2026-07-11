#!/usr/bin/env node
// EXPERIMENTAL — real ACP agent for the ContractPlane governed-run second substrate.
//
// This is a minimal but REAL Agent Client Protocol agent built on the official
// @zed-industries/agent-client-protocol SDK (AgentSideConnection over stdio,
// newline-delimited JSON-RPC 2.0). Its "work" is exactly the producer task the
// governed runs use: it either shells out to the existing Python worker (report
// / aggregate / filter-count / publish) or echoes a recorded claim, writing the
// declared evidence artifact(s) to the paths the client assigns.
//
// Before doing any work it issues a real ACP `session/request_permission`
// request. The ContractPlane client answers that request from the compiled
// contract's authority decision (deny-by-default). On denial the agent performs
// no work and returns `refusal`; on allow it produces the claim and reports it
// back over `session/update`.
//
// It is NOT a language-model agent: the "prompt" carries a JSON task envelope.
// This narrowness is intentional and honest — it exercises the ACP transport and
// permission primitive, not model reasoning.

import * as acp from "@zed-industries/agent-client-protocol";
import { Readable, Writable } from "node:stream";
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

function parseTask(promptBlocks) {
  const textBlock = (promptBlocks || []).find((b) => b && b.type === "text");
  if (!textBlock) throw new Error("prompt is missing a text task envelope");
  return JSON.parse(textBlock.text);
}

function runWorker(task) {
  // Shell out to the exact Python worker the local-process substrate uses.
  const result = spawnSync(task.python, [task.worker, task.assignmentPath], {
    cwd: task.cwd,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(
      `worker exited ${result.status}: ${(result.stderr || "").trim()}`,
    );
  }
  const line = (result.stdout || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .pop();
  if (!line) throw new Error("worker produced no claim on stdout");
  const payload = JSON.parse(line);
  return payload.outputs;
}

function echoClaim(task) {
  // Transport a recorded claim: write the recorded artifact(s) to the assigned
  // evidence paths and return the recorded outputs.
  const artifacts = (task.claim && task.claim.artifact) || {};
  for (const [evidenceId, artifact] of Object.entries(artifacts)) {
    const target = task.evidenceTargets[evidenceId];
    if (!target) throw new Error(`no evidence target for ${evidenceId}`);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, JSON.stringify(artifact), "utf-8");
  }
  return (task.claim && task.claim.outputs) || {};
}

class ContractPlaneAgent {
  constructor(connection) {
    this.connection = connection;
    this.sessions = new Map();
  }

  async initialize(params) {
    return {
      protocolVersion: acp.PROTOCOL_VERSION,
      agentCapabilities: { loadSession: false },
    };
  }

  async newSession(params) {
    const sessionId = "cp-" + Math.random().toString(36).slice(2, 10);
    this.sessions.set(sessionId, { cwd: params.cwd });
    return { sessionId };
  }

  async authenticate() {
    return {};
  }

  async prompt(params) {
    const task = parseTask(params.prompt);
    const sessionId = params.sessionId;

    // Real ACP permission handshake for the action, answered by the client from
    // the compiled contract's authority decision.
    const permission = await this.connection.requestPermission({
      sessionId,
      toolCall: {
        toolCallId: "cp-action",
        title: task.action?.title || "producer action",
        kind: "execute",
        status: "pending",
        rawInput: { capability: task.action?.capability, sideEffects: task.action?.sideEffects },
      },
      options: [
        { optionId: "allow", name: "Allow (authority granted)", kind: "allow_once" },
        { optionId: "deny", name: "Deny (deny-by-default)", kind: "reject_once" },
      ],
    });

    if (
      permission.outcome.outcome !== "selected" ||
      permission.outcome.optionId !== "allow"
    ) {
      await this.connection.sessionUpdate({
        sessionId,
        update: {
          sessionUpdate: "agent_message_chunk",
          content: { type: "text", text: JSON.stringify({ acpDenied: true }) },
        },
      });
      return { stopReason: "refusal" };
    }

    let outputs;
    try {
      outputs = task.mode === "echo" ? echoClaim(task) : runWorker(task);
    } catch (err) {
      await this.connection.sessionUpdate({
        sessionId,
        update: {
          sessionUpdate: "agent_message_chunk",
          content: { type: "text", text: JSON.stringify({ acpError: String(err) }) },
        },
      });
      return { stopReason: "refusal" };
    }

    // Report the claim back over ACP.
    await this.connection.sessionUpdate({
      sessionId,
      update: {
        sessionUpdate: "tool_call_update",
        toolCallId: "cp-action",
        status: "completed",
        rawOutput: { outputs },
      },
    });
    await this.connection.sessionUpdate({
      sessionId,
      update: {
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: JSON.stringify({ outputs }) },
      },
    });
    return { stopReason: "end_turn" };
  }

  async cancel() {}
}

const writableToClient = Writable.toWeb(process.stdout);
const readableFromClient = Readable.toWeb(process.stdin);
const stream = acp.ndJsonStream(writableToClient, readableFromClient);
new acp.AgentSideConnection((conn) => new ContractPlaneAgent(conn), stream);
