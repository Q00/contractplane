# ContractPlane: The Agent Contract Plane

> Whitepaper license: [CC BY 4.0](LICENSES/CC-BY-4.0.txt). Code and the
> machine-readable specification use Apache-2.0; imported Domain Packs retain
> their source licenses.

## Abstract

Agent systems can call models, tools, workflows, and other agents, but their
operating semantics are usually embedded in prompts and application code. A
worker can report success without demonstrating that an artifact exists, that a
policy was followed, or that an independent check accepted the result. Human
guidance is often retained only as chat context. Capabilities improvised during
one run can leak into shared use without a disciplined promotion path. Domain
procedures remain coupled to a particular framework.

ContractPlane proposes an **Agent Contract Plane**: a portable control layer
that translates intent and domain knowledge into a versioned execution
contract, then governs the contract across heterogeneous agent runtimes.

```text
Intent + Domain Pack + Environment -> Execution Contract
```

The contract defines the plan, unit boundaries, authority, budgets, evidence
obligations, human checkpoints, failure semantics, and capability policy for one
run. Producers emit claims; evidence providers record observable facts;
independent verifiers issue verdicts; and only accepted verdicts permit state
transitions. Human steering is represented as a scoped, persistent event rather
than an ephemeral prompt. Missing capabilities follow a governed lifecycle from
local trial to audited promotion and rollback.

ContractPlane is not a model API, an agent-to-agent transport, or an IDE-to-agent
protocol. It is designed to run above frameworks such as Mastra and above
transports such as MCP, A2A, HTTP, and Agent Client Protocol.

> **Publication status:** This paper describes a target architecture. The
> `v0.1.0a1` reference implementation currently provides a DomainPack
> alpha-candidate schema, deterministic `ExecutionPlan` compilation, and an
> experimental local transition kernel. It does not invoke bindings, enforce
> effective authority, issue independent Verdicts, process steering
> invalidation, or implement capability canary/promotion/rollback. RFD 0001 is
> Proposed. See [STATUS.md](STATUS.md).

## 1. The problem

The first generation of agent frameworks answered an important question: how
can an application give a model tools, memory, and a loop? Production systems
must answer a second set of questions:

- What procedure should the system follow for this domain and intent?
- Which decisions are deterministic, agentic, or reserved for a human?
- How should large work be split into parallel units without losing
  resumability or provenance?
- What observable evidence establishes that a unit is complete?
- Who or what is allowed to accept that evidence?
- Which filesystem, network, secret, monetary, and external-mutation authority
  may each unit exercise?
- How does a human redirect a running system without restarting unrelated work?
- How does a newly authored capability graduate from an experiment to a shared
  dependency?
- How can those semantics survive a change in model, framework, or transport?

Today these answers are commonly scattered across system prompts, workflow
code, CI scripts, operator conventions, and tacit knowledge. This creates five
recurring failure modes.

### 1.1 Success is a claim, not proof

Tool exit code zero, an agent's confident prose, and an artifact's mere presence
are weak evidence. A rendered file may be blank, a report may omit a required
section, or a migration may report success while leaving the target state
unchanged. Systems often advance because the producer that did the work also
declared it acceptable.

### 1.2 Domain expertise is not portable

A high-quality agent system contains more than prompts. It contains routing
rules, role boundaries, fan-out strategies, checkpoints, failure taxonomies,
verification techniques, and escalation policies. When those details are tied
to one runtime's source code, moving to another runtime means rebuilding the
operating system of the domain.

### 1.3 Human control is too coarse

“Human in the loop” often means a single approval callback. Real operators need
to issue guidance at different scopes, inspect proposals before an expensive or
irreversible step, and rerun only the work invalidated by a decision.

### 1.4 Self-improvement lacks governance

An agent can write a useful script during a run. That does not establish that the
script is deterministic, safe with secrets, robust across inputs, non-duplicative,
or suitable for other users. Without lifecycle states, self-improvement becomes
unreviewed code accumulation.

### 1.5 Runtime features do not form a portable contract

Modern frameworks already provide strong primitives: typed tools, workflow
graphs, memory, durable execution, evals, and observability. Their application
semantics remain framework-specific. Replacing the scheduler or model can still
change how the domain process behaves.

## 2. Thesis

An agent system should execute a contract, not merely a prompt.

The contract need not predict every model decision. It must specify the
boundaries within which decisions occur and the proof required to accept their
effects. ContractPlane therefore separates three planes:

1. **Contract plane**: intent resolution, domain policy, authority, evidence,
   acceptance, steering, and capability lifecycle.
2. **Execution plane**: scheduling, agents, workflows, tools, storage, and model
   calls.
3. **Transport plane**: local process, HTTP, MCP, A2A, Agent Client Protocol, or
   runtime-native invocation.

ContractPlane aims to standardize the first plane and define adapter boundaries
for the other two. Those semantics remain proposed until accepted through the
project's governance process.

## 3. Naming and protocol boundaries

The product is **ContractPlane**. The formal architecture is the **Agent Contract
Plane**, and [contractplane.dev](https://contractplane.dev/) is the canonical
project and specification namespace. We avoid using the bare acronym “ACP” as
the primary product name because it is already used by unrelated protocols.

- [Agent Client Protocol](https://agentclientprotocol.com/get-started/introduction)
  standardizes communication between code editors/IDEs and coding agents. Its
  documentation describes local JSON-RPC over stdio and evolving remote HTTP or
  WebSocket support.
- The IBM/BeeAI-origin
  [Agent Communication Protocol](https://agentcommunicationprotocol.dev/introduction/welcome)
  standardized REST-based interoperability between agents, applications, and
  humans. Its documentation now states that the project is part of A2A under the
  Linux Foundation.

ContractPlane does not redefine either wire protocol and makes no compatibility
claim merely because the names share letters. An adapter may use those protocols
to execute a ContractPlane unit.

## 4. The contract transformation

The interpreter compiles an execution contract from three inputs.

### 4.1 Intent

Intent captures the requested outcome, supplied inputs, explicit constraints,
and user-visible success conditions. It is not itself an execution plan.

### 4.2 Domain Pack

A Domain Pack packages the operating knowledge of a domain:

- semantic intents and routing rules;
- public entrypoints and private worker roles;
- reusable flow templates and fan-out rules;
- capability requirements and adapter constraints;
- typed input, output, claim, and evidence contracts;
- deterministic and judgment-based verification procedures;
- authority, budget, approval, retention, and escalation policies;
- domain-specific failure classes;
- memory and capability-promotion policy.

A Domain Pack is versioned and content-identifiable. A run records the exact pack
and contract versions it used.

### 4.3 Environment

The environment is a declared observation of runtime conditions: available
adapters and capabilities, platform constraints, granted permissions, secrets
availability, storage, budgets, policy overlays, and relevant artifact metadata.
The environment is not an invitation to discover and use ambient authority.
Only declared observations and grants may influence compilation.

### 4.4 Execution Contract

The compiler resolves ambiguity and produces an immutable contract for the run.
At minimum it contains:

- normalized intent and selected Domain Pack version;
- plan template and resolved unit strategy;
- required capabilities and chosen adapters;
- authority and budget envelopes;
- evidence obligations and accepted verifier policy;
- human approval and steering checkpoints;
- retry, timeout, cancellation, and compensation policy;
- data classification, retention, and redaction policy;
- compatibility and provenance identifiers.

Any material change creates a new contract revision. A revision explicitly
states which completed units remain valid and which are invalidated.

## 5. The proof-carrying execution model

The proposed Agent Contract Plane models execution as:

```text
Plan -> Unit -> Claim -> Evidence -> Verdict -> Transition
```

### 5.1 Plan and unit

A Plan is a dependency graph instantiated from the execution contract. A Unit is
the smallest independently dispatchable and verifiable node in that graph. Unit
boundaries are part of domain knowledge: one transcript chunk, one database
partition, one policy section, or one deployment target may be a unit.

A stable unit key includes the relevant contract revision, normalized inputs,
capability versions, and scoped directives. This permits idempotent reuse of a
confirmed unit and precise invalidation when one dependency changes.

### 5.2 Claim

A Claim is the producer's structured assertion about what it did. It identifies
the unit, outputs, producer, adapter, timestamps, and claimed contract
conditions. A claim is necessary for observability but insufficient for
acceptance.

### 5.3 Evidence

Evidence is an immutable or tamper-evident record of observable facts. Examples
include checksums, schema validation, probes, test results, before/after state,
artifact metadata, citations, screenshots, or sampled media frames. Evidence
records identify the method, tool version, inputs, outputs, and collection time.

ContractPlane distinguishes:

- **mechanical evidence**, produced by deterministic checks;
- **model-assisted evidence**, produced by a model but constrained to a declared
  rubric and provenance;
- **human evidence**, such as an approval, correction, or signed observation.

These classes are not interchangeable unless policy says so.

### 5.4 Verdict

A Verdict evaluates a claim against required evidence and policy. The verifier
must be independent according to the contract's independence rule. Independence
may require a separate process, role, model, organization, or human reviewer.

The core model proposes four portable outcomes:

- `confirmed`: the unit satisfies its acceptance contract;
- `needs_fix`: defects are observable and actionable;
- `needs_human_review`: evidence cannot resolve a reserved judgment;
- `rejected`: the claim or action violates the contract or policy.

Only `confirmed`, or an explicit authorized human override recorded as a new
verdict, may satisfy a required gate.

## 6. Orchestration by waves

ContractPlane combines declarative plans with agent judgment. It does not force
every process into either a fully deterministic workflow or a free-running
agent.

The scheduler identifies all ready units in a **wave**, applies concurrency and
budget policy, and dispatches them through runtime adapters. Fan-out width may
be static or derived from prior evidence, such as file count, transcript
sections, or database partitions. Fan-in does not accept worker completion
messages directly; it consumes confirmed unit outputs.

Retries preserve the unit identity and attempt history. A retry may narrow the
scope or change an adapter only if the contract permits it. A different input,
directive, policy, or capability version creates a distinct unit revision rather
than silently overwriting history.

## 7. The director is in the loop

The target architecture treats a human as a director, not as an emergency
callback.

A Directive is a typed, scoped event. Its scope can address the whole run, a
stage, a unit set, one unit, or an artifact. Before dispatch, the scheduler
resolves all applicable directives and includes them in the unit contract. When
a directive arrives during a run, the interpreter computes its invalidation set
and reruns only affected units and downstream dependants.

Approvals are distinct from steering:

- **steering** changes desired behavior or creative direction;
- **approval** grants a specific authority or accepts a proposed transition;
- **override** accepts known risk and must identify the policy and evidence being
  overridden.

All three are ledger events with actor identity, scope, rationale, and expiry.

## 8. Governed capability evolution

When a required capability is unavailable, the interpreter classifies the gap
before authoring anything.

| Gap | Preferred layer |
|---|---|
| Ambiguous or creative judgment | bounded agent role |
| Small deterministic transform | local tool capability |
| Shared stateful behavior used by several flows | core/runtime capability |
| Browser, service, network, or credential-heavy operation | dedicated integration |

A candidate capability progresses through explicit lifecycle states:

```text
discovered -> local -> trial -> audited -> shared -> deprecated -> retired
                                      \-> rejected
```

Promotion policy can require:

- a machine-readable input/output and permission manifest;
- a mandatory self-test and deterministic error behavior;
- execution in a sandbox with a scrubbed environment;
- static and dependency analysis;
- representative successful and failed runs;
- an independent security and duplication review;
- signed provenance and immutable versioning;
- canary activation and rollback criteria;
- explicit approval before external repository or service mutation.

This model turns self-improvement from “the agent wrote code” into “the system
earned confidence in a versioned capability.”

## 9. Memory is not one thing

Conversation recall is useful but insufficient for operational systems.
ContractPlane separates at least five memory classes:

1. **episodic memory**: what happened during prior runs;
2. **working state**: the current run's bounded, structured state;
3. **policy memory**: approved organizational constraints and exceptions;
4. **preference or taste memory**: human creative choices with provenance and
   scope;
5. **capability memory**: available implementations, evidence of reliability,
   versions, and promotion status.

Each class has a writer policy, reader scope, retention policy, and invalidation
rule. Model-generated summaries cannot silently become policy or shared
capability memory.

## 10. Runtime and transport neutrality

ContractPlane proposes semantic adapter interfaces, not one execution engine.

A runtime adapter is responsible for dispatch, cancellation, streaming,
suspension, and result collection. A transport adapter is responsible for
reaching a tool or agent. The implementation may combine them, but conformance
tests observe their responsibilities separately.

Potential runtime adapters include Mastra, Codex, Claude, LangGraph, Temporal,
or a local reference scheduler. Potential transports include direct function
calls, local CLI, HTTP, MCP, A2A, and Agent Client Protocol.

Framework-native state may supplement the ContractPlane ledger but cannot
replace required portable events. An adapter must not report a capability it
cannot enforce, such as durable suspension or cancellation propagation.

## 11. Relationship to Mastra

Mastra is a broad TypeScript framework for building and deploying agent
applications. Its documented primitives include typed tools, agents, supervisor
delegation, workflows, approvals, snapshots, suspend/resume, time travel,
memory, eval gates, observability, durable agents, and an AgentController.

ContractPlane should adopt rather than recreate many of those ideas:

- Standard JSON Schema at every boundary;
- explicit agent versus workflow semantics;
- snapshot and durable resume support;
- resource/thread memory scopes and subagent isolation;
- approval and cancellation propagation;
- trace/span correlation and asynchronous quality scoring;
- processor-style policy tripwires;
- graph inspection and time-travel debugging.

Its different focus is a portable domain and governance contract. Carefully
qualified:

> Mastra orchestrates agents; ContractPlane governs execution.

This does not imply that Mastra lacks governance features. It means a Mastra
adapter can supply the execution plane while ContractPlane supplies portable
Domain Packs, evidence obligations, scoped steering, unit invalidation, and
capability-promotion semantics. See
[docs/design/mastra-comparison.md](docs/design/mastra-comparison.md).

## 12. Security model

An execution contract is intended to be a security boundary. The target
architecture therefore requires:

- deny-by-default authority and separate grants for read, write, execute,
  network, secrets, spending, and external mutation;
- declared filesystem roots and output paths;
- sandboxing and resource limits for untrusted capabilities;
- secret references instead of secret values in plans, prompts, evidence, or
  ledgers;
- prompt-injection-resistant separation of data and instructions;
- signed or content-addressed Domain Packs, contracts, capabilities, and
  evidence where the threat model requires it;
- explicit approval for irreversible or externally visible effects;
- provenance and redaction throughout traces and evidence;
- independent security review before shared promotion.

The detailed threat model is in [SECURITY.md](SECURITY.md).

## 13. Conformance

A specification without behavioral tests will drift across runtimes.
The project therefore intends to treat conformance fixtures as a first-class
artifact.
An implementation should be testable for:

- deterministic contract compilation from fixed inputs;
- dependency and wave scheduling;
- stable unit identity and precise invalidation;
- claim/evidence/verdict gate enforcement;
- scoped steering and approval behavior;
- cancellation, retry, suspend, and resume semantics;
- least-authority adapter negotiation;
- event ordering and replay;
- capability promotion and rollback policy;
- portable failure reporting.

Conformance levels may distinguish a minimal local interpreter from a durable,
distributed runtime. No implementation should claim full conformance without
publishing the suite version and results.

## 14. Adoption strategy

The proposed sequence is deliberately narrow.

### Phase 1: core contract

Stabilize the object model, event ledger, state machine, authority envelope, and
evidence semantics.

### Phase 2: local reference interpreter

Implement deterministic compilation and a local adapter with no ambient network
or credential authority.

### Phase 3: first Domain Pack

Extract the operating lessons of OpenClip into a media Domain Pack: semantic
routing, per-unit fan-out, human creative checkpoints, mechanical and editorial
verification, resumability, and audited tool promotion.

### Phase 4: second domain

Validate that the abstraction is not video-specific by implementing a domain
with different artifacts and risk, such as incident response or research.

### Phase 5: ecosystem adapters

Add Mastra and other runtime adapters, transport adapters, distributed ledger
storage, visualization, and a public conformance matrix.

## 15. Limits and open questions

ContractPlane cannot make subjective verification objective. It can only make
the evidence class, verifier, rubric, and reserved human judgment explicit.

Independent agents may share model bias. Some contracts will require model
diversity or a human verifier. Event logs can reveal decisions but cannot by
themselves prove that an external system behaved honestly. Distributed
execution introduces clock, lease, duplicate-delivery, and consistency
questions. Capability promotion can still encode organizational bias.

The project must resist scope expansion into a universal agent framework.
Storage engines, model routers, UI systems, and transports should remain adapter
concerns unless a portable semantic requirement cannot be expressed otherwise.

## 16. Conclusion

Reliable agent systems need more than increasingly capable models. They need an
explicit agreement about how intent becomes work, which authority that work may
exercise, what proves it succeeded, how humans can redirect it, and how the
system earns new capabilities.

ContractPlane proposes that agreement as a portable Agent Contract Plane:

```text
Intent + Domain Pack + Environment -> Execution Contract
Plan -> Unit -> Claim -> Evidence -> Verdict
```

The goal is not autonomy without friction. The goal is execution that remains
steerable, inspectable, resumable, and governable as agents and runtimes change.

## References

- Mastra, [documentation index](https://mastra.ai/llms.txt)
- Mastra, [Agents overview](https://mastra.ai/docs/agents/overview)
- Mastra, [Workflows overview](https://mastra.ai/docs/workflows/overview)
- Mastra, [Snapshots](https://mastra.ai/docs/workflows/snapshots)
- Mastra, [Memory](https://mastra.ai/docs/memory/overview)
- Mastra, [Gates and verdicts](https://mastra.ai/docs/evals/gates-and-verdicts)
- Mastra, [Observability](https://mastra.ai/docs/observability/overview)
- Mastra, [Agent Client Protocol integration](https://mastra.ai/docs/agents/acp)
- Agent Client Protocol,
  [Introduction](https://agentclientprotocol.com/get-started/introduction)
- Agent Communication Protocol,
  [Introduction](https://agentcommunicationprotocol.dev/introduction/welcome)

The web sources above are mutable documentation. Statements in this paper were
checked against their public pages on 2026-07-11 and should be revalidated when
used for compatibility decisions.
