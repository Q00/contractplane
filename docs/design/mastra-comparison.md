# ContractPlane and Mastra

Status: Research-backed design comparison

Sources checked: 2026-07-11

ContractPlane entries in this comparison describe the **target architecture**
unless explicitly marked implemented. The `v0.1` reference kernel does not yet
provide a Mastra adapter, effective authority enforcement, independent Verdict
objects, steering invalidation, or capability promotion. See
[../../STATUS.md](../../STATUS.md).

## 1. Executive summary

Mastra is a broad TypeScript framework for building and operating AI
applications. Its public documentation covers agents, typed tools, deterministic
workflows, skills, supervisor agents, approvals, memory, evals, observability,
durable execution, server integrations, and deployment.

ContractPlane should not attempt to become “Mastra with more features.” Its
useful layer is different:

> **Mastra orchestrates agents; ContractPlane governs execution.**

This line describes architectural emphasis, not an absence of governance in
Mastra. Mastra has substantial approval, policy, eval, storage, and runtime
features. ContractPlane proposes a portable agreement above such frameworks:
how domain knowledge is packaged, how intent compiles into an execution
contract, what evidence permits state transitions, how steering invalidates
only affected work, and how a discovered capability earns promotion.

A Mastra adapter is therefore a high-value integration, not a contradiction.

## 2. Method and caveats

This comparison is based on Mastra's public `llms.txt` index and directly linked
documentation. It is not a source-code audit, security assessment, performance
benchmark, or claim about undocumented capabilities.

Where this document says that a ContractPlane concept is “not documented,” it
means the reviewed official pages did not present that concept as a
framework-level contract. It does not prove that no Mastra application can
implement it.

Mastra's web documentation is mutable. Package behavior and status must be
rechecked before implementing an adapter. In particular, Mastra labels
`AgentController` as beta and subject to breaking minor-version changes. Claims
in Mastra's Observational Memory documentation about relative accuracy or cost
are vendor claims and are not treated here as independent benchmark results.

## 3. Mastra's documented architecture

### 3.1 Agents and tools

Mastra describes agents as LLM-driven loops for open-ended tasks. Agents reason
over goals, choose tools, retain memory, and iterate until completion or a stop
condition. Tools are defined with descriptions, typed input and output schemas,
and execution functions. Agents, workflows, and subagents can be exposed to an
agent as tools.

Relevant sources:

- [Agents overview](https://mastra.ai/docs/agents/overview)
- [Tools](https://mastra.ai/docs/agents/using-tools)

### 3.2 Skills

Mastra supports the Agent Skills specification. Skills can be defined inline,
loaded from filesystem paths, attached to a workspace, or resolved dynamically
per request. Agents receive skill discovery and read tools.

Source: [Agent skills](https://mastra.ai/docs/agents/skills)

### 3.3 Supervisor agents

Supervisor agents delegate to described subagents. Mastra documents delegation
hooks, message filtering, memory isolation, cancellation propagation, approval
propagation, iteration monitoring, and task-completion scorers.

Source: [Supervisor agents](https://mastra.ai/docs/agents/supervisor-agents)

### 3.4 Workflows

Mastra workflows provide typed steps and explicit control flow including
sequential, parallel, foreach, branch, loop, and nested workflow composition.
The runtime supports workflow state, streaming, suspend/resume, snapshots,
restart, and time travel.

Relevant sources:

- [Workflows overview](https://mastra.ai/docs/workflows/overview)
- [Control flow](https://mastra.ai/docs/workflows/control-flow)
- [Snapshots](https://mastra.ai/docs/workflows/snapshots)
- [Human in the loop](https://mastra.ai/docs/workflows/human-in-the-loop)
- [Time travel](https://mastra.ai/docs/workflows/time-travel)

### 3.5 Memory

Mastra documents message history, working memory, semantic recall, multi-user
threads, and Observational Memory. Its supervisor flow automatically isolates
subagent memory while forwarding selected parent context. Working memory can be
resource- or thread-scoped and can be schema-based.

Relevant sources:

- [Memory overview](https://mastra.ai/docs/memory/overview)
- [Working memory](https://mastra.ai/docs/memory/working-memory)
- [Observational Memory](https://mastra.ai/docs/memory/observational-memory)

### 3.6 Evals, processors, and observability

Mastra scorers support live asynchronous evaluation, historical trace scoring,
datasets, and CI. Gates require a 1.0 score; threshold-bearing scorers can
produce `passed`, `scored`, or `failed` verdicts. Processors can transform,
block, retry, or emit tripwire events around model interactions. Observability
correlates traces, spans, logs, metrics, cost, and human feedback.

Relevant sources:

- [Scorers overview](https://mastra.ai/docs/evals/overview)
- [Gates and verdicts](https://mastra.ai/docs/evals/gates-and-verdicts)
- [Running scorers in CI](https://mastra.ai/docs/evals/running-in-ci)
- [Processors](https://mastra.ai/docs/agents/processors)
- [Guardrails](https://mastra.ai/docs/agents/guardrails)
- [Observability](https://mastra.ai/docs/observability/overview)

### 3.7 Long-running runtime

Mastra documents durable agents that run the agentic loop inside workflows,
publish events through PubSub, retain cached events for reconnect, and persist
run state. Its beta AgentController manages interactive sessions, modes, model
selection, threads, permissions, follow-up steering, subagents, and display
events.

Relevant sources:

- [Durable agents](https://mastra.ai/docs/long-running-agents/durable-agents)
- [AgentController](https://mastra.ai/docs/agent-controller/overview)

### 3.8 Mastra's Agent Client Protocol support

Mastra's `@mastra/acp` package wraps an Agent Client Protocol-compatible coding
agent executable as a Mastra tool or subagent. The documentation describes
newline-delimited JSON over standard input/output, session creation, streaming,
permission requests, persistent child processes, model selection, and workspace
file operations.

This is the existing **Agent Client Protocol**, not ContractPlane's Agent
Contract Plane. Mastra's documentation states that, without a custom permission
handler, its Agent Client Protocol integration selects the first permission
option returned by the agent. A ContractPlane adapter should instead apply the
Execution Contract's explicit, deny-by-default Authority Envelope.

Source: [Mastra Agent Client Protocol](https://mastra.ai/docs/agents/acp)

## 4. Comparison matrix

| Dimension | Mastra | ContractPlane |
|---|---|---|
| Primary purpose | Build and operate AI applications | Govern portable domain execution contracts |
| Primary artifact | Agent, tool, workflow, runtime configuration | Domain Pack and Execution Contract |
| User entry | Application API, server, Studio, channels | Outcome-oriented Intent Gateway |
| Open-ended work | Agent loop | Runtime adapter executing bounded Unit contracts |
| Deterministic work | Typed workflow graph | Portable Plan mapped to runtime workflow primitives |
| Parallelism | Workflow `.parallel()` and `.foreach()`, supervisor delegation | Named dynamic Units, waves, keyed fan-out/fan-in, precise invalidation |
| Human control | Tool approval, suspend/resume, HITL, AgentController follow-ups | Scoped Directive, Approval, and Override with separate semantics |
| Completion | Agent/workflow result plus optional scorers and gates | Claim is non-terminal; required Evidence and accepted Verdict control transition |
| Evaluation | Live scorers, trace eval, CI gates, completion scorers | Contract-declared evidence obligations, independent verifier policy, portable Verdict |
| State and resume | Memory, workflow snapshots, restart, time travel, durable agents | Portable event ledger and semantic Unit reuse across adapters |
| Memory | Conversation, working, semantic, observational | Episodic, working, policy, preference/taste, and capability memory with writer policy |
| Capability discovery | Tools, MCP, skills, tool/skill search | Typed capability registry plus trust and provenance |
| Capability creation | Developer-defined tools and integrations | Governed local candidate, trial, audit, canary, promotion, rollback |
| Security policy | Approvals, processors, guardrails, workspace/sandbox features | Per-Unit least-authority envelope plus adapter enforcement and promotion policy |
| Interoperability | TypeScript APIs, MCP, A2A, Agent Client Protocol, server adapters | Runtime-neutral semantic layer using those systems as adapters |
| Observability | Rich traces, logs, metrics, cost, feedback, Studio | Portable correlation and ledger requirements; reuses runtime observability |
| Deployment | Broad server and cloud deployment surface | Not defined by core; delegated to runtime adapters |

## 5. What ContractPlane should adopt

### 5.1 Standard schemas at every boundary

Mastra's typed tool and workflow interfaces are a strong precedent.
ContractPlane should publish JSON Schemas for Intent, Domain Pack metadata,
Execution Contract, Unit, Claim, Evidence, Verdict, Directive, Approval, and
portable events.

### 5.2 Explicit agent/workflow distinction

Mastra recommends agents for open-ended tasks and workflows for predetermined
control flow. ContractPlane should preserve this distinction while allowing one
Plan to contain deterministic and judgment-bearing Units.

### 5.3 Composable primitives

Mastra can expose agents and workflows as tools. ContractPlane adapters should
likewise permit one Unit implementation to be a tool, agent, workflow, remote
agent, or nested ContractPlane run, while preserving one portable Claim and gate
boundary.

### 5.4 Durable suspend and resume

Mastra's snapshots, persistent suspended runs, time travel, and durable streams
are valuable execution-plane features. The adapter should map them to portable
events without pretending that a runtime snapshot alone is a portable ledger.

### 5.5 Approval and cancellation propagation

Mastra propagates subagent tool approval and cancellation through delegation.
ContractPlane should require adapters to declare and test whether they can
enforce equivalent propagation.

### 5.6 Scoped memory and isolation

Mastra's resource/thread distinction, read-only working memory, and subagent
isolation are useful implementation patterns. ContractPlane adds explicit policy
and capability memory classes but should map compatible scopes where possible.

### 5.7 Observability correlation

Mastra's trace/span/log/metric/feedback correlation is more complete than a new
framework should rebuild initially. A Mastra adapter should attach portable Run,
Unit, Attempt, Claim, Evidence, and Verdict identifiers to native spans.

### 5.8 Runtime and policy processors

Mastra's processors and tripwires demonstrate a practical interception model.
ContractPlane can map pre-dispatch policy, post-claim checks, redaction, budget
guards, and retry feedback through adapter-native processors when their
semantics match.

### 5.9 Developer inspection

Mastra Studio's workflow graph, live status, trace inspection, and evaluation
views are strong UX references. ContractPlane should eventually visualize the
effective contract, pending gates, evidence, invalidation, and authority—not
just agent messages.

## 6. ContractPlane's distinct opportunity

### 6.1 Domain Packs as portable operating systems

Mastra skills package reusable instructions and workflows package executable
control flow. ContractPlane combines intent routing, roles, flow templates,
fan-out boundaries, evidence requirements, authority, human checkpoints,
failure taxonomies, and capability lifecycle into one versioned Domain Pack.

### 6.2 Proof-carrying execution

Mastra provides scorer gates and task-completion scoring. ContractPlane makes a
stronger portable state invariant: producer completion is a Claim, not accepted
completion. The contract names required Evidence, evidence class, freshness,
and verifier independence before execution begins.

### 6.3 Scoped steering and semantic invalidation

Mastra supports follow-ups, steering, suspension, and workflow replay.
ContractPlane gives a Directive a portable target and makes it part of Unit
identity, enabling a runtime-independent calculation of exactly which accepted
work becomes stale.

### 6.4 Governed capability evolution

The reviewed Mastra documentation explains how developers define, discover,
approve, and invoke tools and skills. It does not document a framework-level
pipeline in which a runtime-discovered gap becomes a local candidate, earns
trust through sandboxed tests and representative runs, passes an independent
audit, enters canary use, and is promoted or rolled back. That lifecycle is a
central ContractPlane differentiator.

### 6.5 Institutional memory

Mastra's memory model is rich for conversations and long-running agents.
ContractPlane treats policy, preference/taste, and capability reliability as
separate institutional memory classes with different writers and promotion
rules. An agent-generated observation cannot silently become policy.

### 6.6 Cross-runtime conformance

Mastra is itself a runtime framework. ContractPlane's value depends on an
implementation-neutral event and state model, plus fixtures that demonstrate
equivalent contract behavior across runtimes.

## 7. Proposed Mastra adapter

### 7.1 Mapping

| ContractPlane | Mastra implementation candidate |
|---|---|
| Intent Gateway | server route, channel, or AgentController session |
| Domain Pack role | Agent or skill |
| deterministic Unit | tool or workflow step |
| agentic Unit | Agent or supervisor subagent |
| Plan | workflow graph or ContractPlane scheduler invoking Mastra primitives |
| wave fan-out | `.parallel()`, `.foreach()`, or concurrent agent calls |
| Approval | tool approval or workflow `suspend()`/`resume()` |
| Directive | AgentController follow-up plus ContractPlane ledger event |
| Runtime checkpoint | workflow snapshot or durable-agent state |
| mechanical Evidence | tool/check output stored as ContractPlane Evidence |
| model-assisted Evidence | Mastra scorer output with method provenance |
| Verdict | ContractPlane gate reducer; optionally backed by Mastra scorer/workflow |
| Telemetry | Mastra spans annotated with portable identifiers |
| Working memory | Mastra schema-based working memory with explicit scope |

### 7.2 Ownership boundary

The adapter must not let native convenience erase portable semantics.

In the proposed adapter boundary, ContractPlane would own:

- selected Domain Pack and Execution Contract revision;
- stable Unit identity and semantic invalidation;
- Authority Envelope and required adapter feature set;
- required Evidence and Independence Policy;
- portable Verdict and transition;
- Directive, Approval, and Override events;
- capability trust and promotion state;
- portable ledger export.

Mastra may own:

- agent and workflow execution;
- model and tool integration;
- runtime snapshots and PubSub;
- native memory storage;
- server, auth, channels, and deployment;
- rich tracing and Studio inspection.

### 7.3 Adapter risks

- AgentController is documented as beta; bind to a tested version range.
- Native scorer results are not automatically independent Evidence. The
  contract must inspect scorer, model, and producer identity.
- Native memory may contain more context than a Unit is authorized to read.
- Function-based approval policy may not serialize in every durable context;
  compile policy into supported runtime primitives or fail compatibility.
- Runtime snapshots may contain sensitive fields and are not portable exports.
- The Mastra Agent Client Protocol integration's permission default must not
  bypass ContractPlane authority.

## 8. Competitive positioning

ContractPlane should not claim:

- more model providers, integrations, deployment targets, or UI features than
  Mastra;
- that Mastra lacks approval, verification, durability, memory, or governance;
- drop-in compatibility before an adapter and conformance results exist;
- superior performance without benchmarks.

It can credibly claim a different design target:

> ContractPlane packages domain execution policy into portable contracts whose
> progress is gated by evidence, whose human steering is scoped and replayable,
> and whose capabilities are promoted through an auditable lifecycle.

## 9. Sources

- [Mastra documentation index](https://mastra.ai/llms.txt)
- [Agents overview](https://mastra.ai/docs/agents/overview)
- [Tools](https://mastra.ai/docs/agents/using-tools)
- [Agent skills](https://mastra.ai/docs/agents/skills)
- [Supervisor agents](https://mastra.ai/docs/agents/supervisor-agents)
- [Agent approval](https://mastra.ai/docs/agents/agent-approval)
- [Mastra Agent Client Protocol](https://mastra.ai/docs/agents/acp)
- [Workflows overview](https://mastra.ai/docs/workflows/overview)
- [Workflow control flow](https://mastra.ai/docs/workflows/control-flow)
- [Snapshots](https://mastra.ai/docs/workflows/snapshots)
- [Human in the loop](https://mastra.ai/docs/workflows/human-in-the-loop)
- [Time travel](https://mastra.ai/docs/workflows/time-travel)
- [Memory overview](https://mastra.ai/docs/memory/overview)
- [Working memory](https://mastra.ai/docs/memory/working-memory)
- [Observational Memory](https://mastra.ai/docs/memory/observational-memory)
- [Scorers overview](https://mastra.ai/docs/evals/overview)
- [Gates and verdicts](https://mastra.ai/docs/evals/gates-and-verdicts)
- [Running scorers in CI](https://mastra.ai/docs/evals/running-in-ci)
- [Processors](https://mastra.ai/docs/agents/processors)
- [Guardrails](https://mastra.ai/docs/agents/guardrails)
- [Observability](https://mastra.ai/docs/observability/overview)
- [Durable agents](https://mastra.ai/docs/long-running-agents/durable-agents)
- [AgentController](https://mastra.ai/docs/agent-controller/overview)
- [Mastra repository license](https://github.com/mastra-ai/mastra/blob/main/LICENSE.md)
- [Agent Client Protocol introduction](https://agentclientprotocol.com/get-started/introduction)
- [Agent Communication Protocol introduction](https://agentcommunicationprotocol.dev/introduction/welcome)

Mastra's repository states that content outside designated `ee/` directories is
available under Apache License 2.0, while those enterprise directories have a
separate license. Concepts may be independently implemented, but copying code
requires checking the exact source path and current license.
