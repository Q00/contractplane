# ContractPlane Architecture

Status: Draft target architecture

Formal architecture: **Agent Contract Plane**

## 1. Architectural objective

ContractPlane provides a portable control layer between an outcome-oriented
request and the runtime-specific agents, workflows, and tools that perform the
work.

The diagrams and components below describe the intended architecture, not the
complete `v0.1` runtime. Today the project validates a DomainPack alpha
candidate, compiles deterministic `ExecutionPlan` waves, and exposes an
experimental local transition kernel. It does not invoke bindings, enforce
authority, issue independent Verdicts, process scoped invalidation, or manage
capability canaries and rollback. See [../../STATUS.md](../../STATUS.md).

```text
Intent + Domain Pack + Environment -> Execution Contract
```

The architecture is designed so that domain semantics, authority, proof, human
steering, and capability trust survive a change in model or execution runtime.

## 2. The three planes

```text
+--------------------------------------------------------------+
| Contract plane                                                |
| intent | domain pack | contract | policy | evidence | ledger |
+--------------------------------------------------------------+
                         adapter boundary
+--------------------------------------------------------------+
| Execution plane                                               |
| scheduler | agents | workflows | tools | memory | storage     |
+--------------------------------------------------------------+
                         adapter boundary
+--------------------------------------------------------------+
| Transport plane                                               |
| direct call | CLI | HTTP | MCP | A2A | Agent Client Protocol |
+--------------------------------------------------------------+
```

The contract plane is intended to become normative for ContractPlane after its
RFDs and schemas are accepted. It is currently a draft design. Execution and
transport planes remain implementation choices exposed through declared
adapters.

The canonical project and specification namespace is
[`contractplane.dev`](https://contractplane.dev/); versioned schemas and object
identifiers are rooted there.

This separation also prevents naming confusion. ContractPlane is not Agent
Client Protocol and not the IBM/BeeAI-origin Agent Communication Protocol. Those
protocols may appear in the transport plane.

## 3. System context

```text
                    +------------------+
                    | Human Director   |
                    +---------+--------+
                              | intent, directive,
                              | approval, override
                              v
+-------------+     +---------+----------+     +----------------+
| Application +---->| ContractPlane      +---->| Event / Object |
| or CLI      |     | Interpreter        |     | Store          |
+-------------+     +---------+----------+     +----------------+
                              |
                     execution contracts
                              |
                              v
                    +---------+----------+
                    | Wave Scheduler     |
                    +----+----------+----+
                         |          |
                  dispatch          | verify
                         v          v
                   +-----+---+  +---+------+
                   | Runtime |  | Evidence |
                   | Adapter |  | Gate     |
                   +-----+---+  +---+------+
                         |          |
                         v          v
                   agents/tools   verifier/human
```

## 4. Core components

### 4.1 Intent Gateway

Responsibilities:

- accept requests from a CLI, API, UI, or host agent;
- authenticate the actor where required;
- normalize outcome, inputs, constraints, and success conditions;
- retain the original request as provenance;
- mark untrusted embedded content as data, not instruction or policy.

The gateway does not choose arbitrary worker roles. It produces a typed Intent
for the Contract Interpreter.

### 4.2 Domain Pack Registry

Responsibilities:

- index Domain Pack metadata without executing pack content;
- resolve names, semantic intents, versions, compatibility ranges, and
  signatures;
- expose schemas, policies, flow templates, and capability requirements;
- enforce source and trust policy;
- retain immutable versions and revocation status.

Registry implementations may be filesystem-based, package-based, or remote.
Discovery metadata and executable content must remain distinguishable.

### 4.3 Environment Inspector

Responsibilities:

- enumerate installed and remotely available adapters and capabilities;
- collect declared platform constraints and resource limits;
- resolve policy overlays and current grants;
- report storage, sandbox, and durability features;
- expose secret references without reading secret values;
- create a signed or content-addressed Environment Snapshot when required.

The inspector reports availability. It does not grant authority.

### 4.4 Contract Compiler

Responsibilities:

- select a compatible Domain Pack and flow;
- resolve inputs, defaults, policy overlays, and adapter choices;
- bind schemas and versions;
- compute authority and budget envelopes;
- instantiate required gates, approvals, and memory scopes;
- reject unsatisfied requirements before dispatch;
- emit an immutable Execution Contract and diagnostic report.

Compilation should be deterministic over canonical inputs. If model assistance
is used for semantic routing, its proposal must be resolved into an explicit,
reviewable choice; the canonical compiler output cannot depend on hidden model
state.

### 4.5 Plan Builder

Responsibilities:

- instantiate the contract's flow as a dependency graph;
- expand static units and define dynamic fan-out rules;
- attach unit schemas, capability requirements, gates, policy, and directives;
- compute stable Unit keys;
- validate fan-in contracts and cycle policy.

Dynamic expansion is driven by accepted prior outputs. For example, an ingest
unit may establish a chunk count; the builder then creates one transcription
unit per chunk.

### 4.6 Wave Scheduler

Responsibilities:

- select Units whose dependencies and approvals are satisfied;
- resolve effective directives and authority;
- enforce concurrency, rate, resource, and monetary limits;
- acquire leases and dispatch attempts through adapters;
- propagate cancellation and suspension;
- schedule evidence collection and verdict evaluation;
- checkpoint portable events before and after effects where feasible.

A **wave** is a set of dependency-ready Units that can execute concurrently
under current policy. A wave is an operational concept, not a guarantee that all
Units start or finish simultaneously.

### 4.7 Runtime Adapter Host

Responsibilities:

- match required features to adapter declarations;
- translate a portable Unit into runtime-native invocation;
- stream progress without treating progress as a Claim;
- return a structured Claim or typed failure;
- expose cancellation, suspend/resume, and durability behavior honestly;
- map runtime telemetry to portable correlation identifiers.

Adapters may target Mastra, Codex, Claude, LangGraph, Temporal, a local process
runner, or another system. Framework-specific extensions live in namespaced
contract fields.

### 4.8 Evidence Collector

Responsibilities:

- execute declared checks against the correct subject and attempt;
- collect deterministic evidence before more expensive model or human checks;
- record method, version, input and output references, timestamps, and integrity;
- keep evidence payloads separate from redacted ledger metadata when required;
- report collection failure as an evidence failure, not as a passing result.

Evidence collectors are capabilities with their own authority and provenance.

### 4.9 Verdict Engine

Responsibilities:

- verify that required evidence is present, fresh, and valid;
- enforce verifier independence policy;
- evaluate domain rubrics and policy gates;
- issue a portable Verdict with findings and required fix information;
- prevent downstream transition without an accepted verdict;
- route reserved judgment to a human.

The engine may invoke deterministic policy, an independent agent, a human, or a
combination. A producer cannot satisfy an independent gate by changing its own
Claim.

### 4.10 Steering and Approval Manager

Responsibilities:

- accept Directives, approvals, denials, and overrides;
- authenticate actors and verify their authority;
- scope and order directives;
- compute the affected Unit and downstream invalidation set;
- wake suspended runs;
- expire grants and directives;
- preserve rationale and resolution status.

Creative steering never implies permission. Permission never silently changes
the requested outcome.

### 4.11 Ledger and Object Store

The architecture separates small ordered control events from potentially large
or sensitive immutable objects.

- **Ledger**: append-only events and references needed to reconstruct portable
  state.
- **Object store**: contracts, plans, artifacts, evidence payloads, schemas, and
  protected data.
- **Index/projection**: disposable views for current status, queries, and UI.

The ledger is the source for portable control state. A framework's internal
snapshot can accelerate recovery but cannot replace required portable events.

### 4.12 Capability Registry and Promotion Controller

Responsibilities:

- discover capabilities by typed manifest;
- prevent duplicate or incompatible registration;
- store trust tier, provenance, test history, review, and revocation;
- run promotion policy and canary checks;
- separate proposal generation from external publication;
- support deprecation, rollback, and emergency revocation.

## 5. Core data relationships

```text
DomainPackVersion ----+
                      |
Intent ---------------+--> ExecutionContractRevision --> PlanRevision
EnvironmentSnapshot --+                                  |
PolicySet ------------+                                  +--> UnitRevision
DirectiveSet ---------+                                         |
                                                                +--> Attempt
                                                                       |
                                                                       +--> Claim
                                                                       +--> Evidence[*]
                                                                       +--> Verdict[*]
```

Capability versions, adapter versions, grants, budgets, and memory bindings are
referenced by the Execution Contract and narrowed at the Unit level.

## 6. Identifiers and immutability

ContractPlane distinguishes identity from revision.

- A Run has stable identity across contract revisions.
- Each Execution Contract and Plan revision is immutable.
- A logical Unit can have multiple Unit revisions and attempts.
- Claims, Evidence, Verdicts, Directives, and Approval records are immutable;
  corrections append superseding records.
- Large objects should be content-addressed when privacy and storage policy
  permit.

A Unit key should be derived from canonical semantic inputs:

```text
unit_key = hash(
  spec_profile,
  contract_revision,
  node_id,
  normalized_unit_input,
  capability_versions,
  relevant_directives,
  acceptance_policy_version
)
```

Secret values are represented by stable opaque references or policy-approved
version identifiers, never embedded in the key.

## 7. Compilation sequence

```text
Director       Gateway       Registry      Inspector      Compiler
   | intent       |             |              |             |
   +------------->| normalize   |              |             |
   |              +------------>| discover     |             |
   |              |<------------+ candidates   |             |
   |              +--------------------------->| snapshot    |
   |              |<---------------------------+ environment |
   |              +----------------------------------------->|
   |              |          compile and validate            |
   |              |<-----------------------------------------+
   |              | contract or typed diagnostics            |
```

No worker dispatch occurs until compilation and contract validation succeed.
If more human information is required, the compiler returns a typed question or
ambiguity instead of selecting a materially different policy by guesswork.

## 8. Unit execution sequence

```text
Scheduler       Adapter        Producer      Collector       Verifier
    | dispatch     |              |              |              |
    +------------->| invoke       |              |              |
    |              +------------->| work         |              |
    |              |<-------------+ claim        |              |
    |<-------------+ structured claim            |              |
    +-------------------------------------------->| collect      |
    |<--------------------------------------------+ evidence     |
    +---------------------------------------------------------->|
    |                                  claim + required evidence |
    |<----------------------------------------------------------+
    |                                      verdict               |
    | transition only if policy accepts the verdict              |
```

Progress events may stream throughout this sequence. They do not change Unit
acceptance state.

## 9. Portable state machines

### 9.1 Run states

```text
created -> compiling -> ready -> running -> completed
                    \-> rejected
ready/running -> suspended -> running
ready/running/suspended -> cancelling -> cancelled
running -> failed
```

An implementation may add internal states but must map them to portable states.

### 9.2 Unit states

```text
planned -> ready -> running -> claimed -> verifying -> confirmed
                    |            |           |
                    |            |           +-> needs_fix -> ready
                    |            |           +-> needs_human_review -> suspended
                    |            |           +-> rejected
                    |            +-> failed -> ready (if retryable)
                    +-> cancelled

confirmed -> invalidated -> ready
```

`claimed` is intentionally not terminal. `confirmed` is the accepted completion
state for a required gate.

## 10. Directives and invalidation

Directive precedence is resolved from explicit policy, not message recency
alone. A typical order is:

1. immutable safety and organizational policy;
2. authorized run-specific constraints;
3. scoped human directive;
4. Domain Pack defaults;
5. worker preference.

When a Directive changes, the interpreter:

1. identifies the addressed targets;
2. finds Units whose semantic inputs include that target;
3. appends invalidation events for affected confirmed Unit revisions;
4. recursively invalidates downstream Units whose accepted inputs changed;
5. retains unrelated confirmed Units;
6. compiles a new contract or plan revision when required;
7. schedules the minimal valid rerun set.

An adapter that can only resume at stage or workflow granularity must declare
that limitation. It may rerun more work operationally, but portable state still
records the precise semantic invalidation set.

## 11. Evidence architecture

Evidence requirements belong to the contract, not to an after-the-fact QA
script. Each requirement defines:

- subject and claimed property;
- evidence class;
- collector constraints;
- freshness and environment constraints;
- required independence;
- pass rule or rubric;
- severity and whether it blocks progression;
- retention and redaction.

A recommended gate order is:

1. existence, type, schema, and integrity;
2. deterministic domain probes;
3. cross-artifact consistency;
4. model-assisted adversarial review;
5. reserved human judgment.

This ordering reduces cost and prevents an expensive judge from masking a basic
mechanical failure.

## 12. Capability lifecycle architecture

```text
                +----------+
discover ------>| existing |----> use under current trust policy
                +----------+
                      no match
                         |
                         v
                    +---------+
                    |  local  |
                    +----+----+
                         | self-test, manifest, sandbox
                         v
                    +---------+
                    |  trial  |
                    +----+----+
                         | representative runs
                         v
                    +---------+
                    | audited |----> rejected
                    +----+----+
                         | approval / canary
                         v
                    +---------+
                    | shared  |----> deprecated -> retired
                    +---------+          |
                         ^               +-> rollback/revoke
                         +-------------------
```

Tool output and self-test output should be machine-readable. A promotion
controller runs with different authority from the capability author. Publication
to an external repository or registry is a separate, explicitly approved
effect.

## 13. Adapter contracts

### 13.1 Runtime adapter

A runtime adapter declaration should include:

- adapter and implementation version;
- supported ContractPlane profile;
- dispatch mode and supported payload classes;
- structured output fidelity;
- streaming, cancellation, suspension, and resume support;
- durability and duplicate-delivery behavior;
- sandbox and authority enforcement features;
- telemetry and evidence hooks;
- known semantic limitations.

The host chooses an adapter only after matching those declarations to the Unit.

### 13.2 Transport adapter

A transport adapter should include:

- addressing and discovery;
- authentication and channel protection;
- serialization and content-type behavior;
- sync, async, and streaming semantics;
- timeout, retry, idempotency, and delivery guarantees;
- remote error mapping;
- file or artifact transfer behavior;
- supported permission negotiation.

Agent Client Protocol and A2A adapters translate transport semantics; they do
not define ContractPlane acceptance or capability promotion.

### 13.3 Framework adapter example: Mastra

A Mastra adapter can map:

- a Unit to a Mastra agent, workflow, or tool;
- Plan edges to workflow control flow;
- suspension and approval to Mastra suspend/resume and tool approval;
- runtime snapshots to recovery acceleration;
- spans and scorer results to ContractPlane telemetry and Evidence candidates;
- supervisor delegation to internal role dispatch.

ContractPlane still owns the portable Execution Contract, Unit key, required
Evidence, Verdict, Directive, invalidation, and capability lifecycle events.

## 14. Memory architecture

Memory is exposed through typed bindings rather than one unscoped transcript.

| Class | Typical scope | Default writer |
|---|---|---|
| Episodic | actor, project, or run | ledger projection / approved summarizer |
| Working | Unit, stage, or run | designated role or state reducer |
| Policy | organization or domain | authorized policy maintainer |
| Preference/taste | actor and domain | human or approved reflection process |
| Capability | installation or organization | promotion controller |

Each binding specifies read-only or read/write access. Subagents should receive
the minimum slice needed by their Unit. Full parent context is not portable
default behavior.

## 15. Security boundaries

Primary trust boundaries are:

1. untrusted intent and attached content entering the gateway;
2. Domain Pack discovery versus pack activation;
3. compiler and policy engine versus runtime adapter;
4. scheduler versus untrusted capability process;
5. protected object store versus prompts, logs, and exports;
6. local reversible effects versus external or irreversible mutation;
7. capability author versus independent auditor and promoter;
8. producer versus verifier.

See [../../SECURITY.md](../../SECURITY.md) for the threat model and controls.

## 16. Distributed execution

Distributed implementations must account for:

- duplicate dispatch and at-least-once delivery;
- worker leases, heartbeats, and fencing tokens;
- concurrent claims for one Unit attempt;
- event ordering and idempotent reducers;
- clock skew;
- network partitions during approval or cancellation;
- effects committed before acknowledgment;
- artifact consistency and evidence availability;
- verifier isolation and compromised workers.

The portable model does not require exactly-once execution. It requires honest
representation of attempts and effects. External side effects should use
idempotency keys, reconciliation, or compensation where available.

## 17. Observability

Every runtime-native trace should carry portable correlation identifiers.
Recommended spans include:

- contract compilation;
- plan expansion;
- Unit queue and attempt;
- adapter call;
- model or tool call;
- evidence collection;
- verdict evaluation;
- approval wait;
- capability promotion gate.

Metrics may include queue time, attempt duration, retries, token and monetary
cost, evidence latency, human wait time, invalidated work, gate failure classes,
and capability reliability. Metrics never substitute for the ledger.

## 18. Extension policy

Extensions are namespaced and classified as:

- **annotation**: ignorable metadata with no control effect;
- **portable optional semantic**: standardized but profile-dependent behavior;
- **adapter semantic**: runtime-specific behavior that may reduce portability;
- **security semantic**: authority or policy behavior that must fail closed when
  unsupported.

An extension must state its class. Unknown security semantics are a compilation
error.

## 19. Reference mapping from OpenClip

OpenClip provides the first substantial extraction source:

| OpenClip lesson | ContractPlane primitive |
|---|---|
| `$oc` public entry, internal workers | Intent Gateway + private Domain Pack roles |
| YAML flow with per-stage fan-out | Plan template + dynamic Unit expansion |
| `TASK/DELIVERABLE/SCOPE/STEERING/VERIFY` | Unit contract |
| worker JSON result | Claim |
| `oc verify` output | mechanical Evidence |
| independent adversarial verifier | Verdict and Independence Policy |
| scoped `oc steer` | Directive |
| project ledger and keyed resume | portable event ledger + Unit key |
| local/shared toolbox tiers | Capability lifecycle |
| self-test, scrubbed run, audit, proposal | promotion gates and external effect boundary |
| accumulated creative taste | preference/taste memory |

The architecture must also correct limitations of a single-machine media
harness: raw shell strings become typed actions, prompt-only roles gain schemas,
the ledger gains transactional adapters, and tool review gains stronger
sandbox, provenance, canary, and rollback semantics.

## 20. Architectural invariants

1. Contract compilation precedes effectful dispatch.
2. A producer Claim cannot satisfy an independent gate.
3. Downstream Units consume accepted outputs.
4. Delegation cannot widen authority.
5. Steering cannot grant authority.
6. Material semantic changes produce new revisions and explicit invalidation.
7. Capability registration and capability promotion are separate operations.
8. Portable control state can be rebuilt without model-private reasoning or
   secret values.
9. Adapters report limitations rather than simulate unsupported guarantees.
10. Shared acronym does not imply protocol compatibility.
