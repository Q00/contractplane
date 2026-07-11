# ContractPlane Requirements

Status: Draft; target requirements, not a `v0.1` implementation claim

Audience: specification authors, runtime implementers, Domain Pack authors, and
security reviewers

## 1. Purpose

This document defines the initial requirements for ContractPlane, whose formal
architecture is the **Agent Contract Plane**. ContractPlane compiles a human or
application intent, a versioned Domain Pack, and an explicitly observed
environment into an inspectable Execution Contract.

The current implementation does not yet perform that full compilation. It
validates the DomainPack alpha candidate, compiles an `ExecutionPlan`, and
provides an experimental local state kernel. RFD 0001 is Proposed. See
[../../STATUS.md](../../STATUS.md) for the implemented subset and explicit
limitations. Requirements below are acceptance targets unless they say
otherwise.

```text
Intent + Domain Pack + Environment -> Execution Contract
```

The contract governs planning, dispatch, authority, evidence, acceptance,
steering, resumption, and capability evolution across replaceable agent
runtimes and transports.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are to be interpreted as described by BCP 14 when, and only when,
they appear in all capitals.

## 2. Scope

### 2.1 In scope

- a portable core object and event model;
- Domain Pack discovery and version binding;
- deterministic contract compilation from declared inputs;
- typed plans, unit-level scheduling, fan-out, fan-in, retry, and resume;
- explicit authority and budget envelopes;
- structured producer claims, evidence, verifier independence, and verdicts;
- scoped human steering, approvals, and overrides;
- append-only execution history and replay;
- governed capability discovery, trial, promotion, deprecation, and rollback;
- runtime and transport adapter contracts;
- conformance fixtures and levels;
- security and privacy requirements for the contract plane.

### 2.2 Out of scope

The initial specification does not define:

- a new model API or inference protocol;
- an editor-to-agent wire protocol;
- a general agent-to-agent message transport;
- a mandatory workflow engine, storage database, UI, model, or programming
  language;
- a universal ontology for every domain;
- unconstrained autonomous code installation or self-modification;
- a hosted control-plane service;
- a replacement for MCP, A2A, Agent Client Protocol, or framework-native tools.

## 3. Naming boundary

The product name is **ContractPlane** and the architecture name is **Agent
Contract Plane**. Documentation MUST NOT imply protocol compatibility based only
on the acronym ACP.

The canonical project and specification namespace is
[`contractplane.dev`](https://contractplane.dev/). Machine-readable identifiers
SHOULD use versioned names under that namespace. Ownership of the namespace does
not by itself establish conformance or compatibility.

- Agent Client Protocol standardizes editor/IDE and coding-agent communication.
- The IBM/BeeAI-origin Agent Communication Protocol focused on agent,
  application, and human interoperability and now documents its incorporation
  into A2A under the Linux Foundation.

Either can be used by an adapter. Neither is the ContractPlane core protocol.

## 4. Stakeholders

- **Director**: the human accountable for the requested outcome and reserved
  decisions.
- **Application integrator**: embeds an interpreter or invokes one through an
  API.
- **Domain Pack author**: encodes domain flows, roles, checks, and policies.
- **Runtime adapter author**: maps portable units to a concrete agent or workflow
  runtime.
- **Capability author**: implements a tool or integration used by units.
- **Verifier**: evaluates claims and evidence under an independence policy.
- **Operator**: monitors, resumes, cancels, and investigates runs.
- **Security reviewer**: reviews authority, isolation, provenance, and promotion.
- **Auditor**: reconstructs what occurred and why from retained records.

## 5. System goals

ContractPlane SHALL make it possible to:

1. package domain operating knowledge independently of one runtime;
2. know what will run and under which authority before effects occur;
3. split work into stable units that can fan out and resume independently;
4. distinguish a producer's success claim from accepted proof;
5. retain human steering and approvals as scoped, attributable events;
6. evolve reusable capabilities through an auditable promotion lifecycle;
7. replay and explain decisions after model, process, or infrastructure failure;
8. compare implementations through an implementation-neutral conformance suite.

## 6. Functional requirements

### 6.1 Intent, discovery, and compilation

**CP-FR-001 — Intent envelope.** The interpreter MUST accept a typed Intent
containing the requested outcome, inputs, explicit constraints, actor identity,
and user-visible success conditions. It MUST retain the original user request
as provenance without treating untrusted content as policy.

**CP-FR-002 — Domain Pack discovery.** The interpreter MUST discover candidate
Domain Packs by declared metadata and compatibility, not by loading arbitrary
executable code. It MUST bind one explicit version or return an ambiguity or
incompatibility result.

**CP-FR-003 — Environment observation.** Compilation MUST use a typed Environment
Snapshot containing available adapters, capability versions, platform
constraints, storage, policy overlays, budgets, and grants. Ambient authority
MUST NOT be inferred merely because a credential or executable exists.

**CP-FR-004 — Contract compilation.** Given the same canonical Intent, Domain
Pack version, Environment Snapshot, policy inputs, and compiler version, a
conforming deterministic compiler MUST produce semantically equivalent
Execution Contracts.

**CP-FR-005 — Validation before dispatch.** The compiler MUST reject unresolved
required inputs, incompatible adapters, unsatisfied authority, invalid schemas,
cycles forbidden by the flow policy, and missing required gates before any unit
is dispatched.

**CP-FR-006 — Contract revision.** A material change to intent, policy,
authority, selected capability, or applicable directive MUST create a new
contract revision. The revision MUST identify which prior unit results remain
valid and why.

### 6.2 Planning and execution

**CP-FR-007 — Plan graph.** An Execution Contract MUST resolve to a typed Plan
whose dependency edges, gates, and fan-out rules are inspectable without
executing workers.

**CP-FR-008 — Unit boundary.** Every executable node MUST resolve to one or more
Units with typed inputs, expected outputs, required capabilities, authority,
budget, timeout, retry policy, evidence obligations, and acceptance rule.

**CP-FR-009 — Stable unit identity.** A Unit MUST have a stable key derived from
the contract revision and all inputs that affect semantic output, including
applicable directives and capability versions. Secret values MUST NOT be
included directly in the key.

**CP-FR-010 — Wave scheduling.** The scheduler MUST identify dependency-ready
Units and MAY dispatch them concurrently within declared concurrency, resource,
and budget bounds. A fan-in MUST consume accepted outputs, not unverified
completion messages.

**CP-FR-011 — Adapter negotiation.** A runtime adapter MUST declare supported
features and constraints. The scheduler MUST NOT rely on cancellation,
suspension, durability, streaming, or sandbox guarantees the adapter does not
declare and pass in conformance tests.

**CP-FR-012 — Attempt history.** Retries MUST retain prior attempts and failure
evidence. Implementations MUST NOT overwrite the history of a failed or
superseded attempt.

**CP-FR-013 — Cancellation and timeout.** Runs and Units MUST support explicit
cancellation and timeout outcomes. An adapter MUST report whether cancellation
was requested, observed, and confirmed; request acknowledgment alone MUST NOT be
represented as effect cessation.

**CP-FR-014 — Resumption.** A run MUST be resumable from its ledger. Confirmed
Units SHOULD be reused when their keys and acceptance policies remain valid.
Unconfirmed, invalidated, or expired Units MUST be reconsidered.

### 6.3 Authority and budgets

**CP-FR-015 — Explicit authority.** Each Unit MUST carry an Authority Envelope.
At minimum, filesystem read, filesystem write, process execution, network,
secret access, monetary spend, and external mutation MUST be separately
expressible.

**CP-FR-016 — Least authority.** Runtime adapters MUST deny operations outside
the Unit's effective Authority Envelope. A parent grant MUST be narrowed, never
implicitly broadened, during delegation.

**CP-FR-017 — Budget enforcement.** Token, monetary, wall-time, CPU, memory,
storage, network, and attempt limits MUST be representable. A budget breach MUST
produce a typed event and policy outcome.

**CP-FR-018 — Approval.** Policy MUST be able to suspend a proposed action before
an effect and request approval with the exact action, arguments or redacted
summary, authority requested, scope, and expiry. Approval MUST bind to that
request or a deliberately declared broader grant.

**CP-FR-019 — External mutation.** Branch creation, push, pull request creation,
deployment, publication, messaging, purchase, deletion, and comparable external
effects MUST be distinguishable from local reversible work and MAY require
explicit approval by policy.

### 6.4 Claims, evidence, and verdicts

**CP-FR-020 — Structured claim.** A producer MUST return a Claim bound to one
Unit attempt. The Claim MUST identify outputs, claimed conditions, producer,
runtime adapter, capability versions, and timestamps.

**CP-FR-021 — Evidence obligation.** Each gated Unit MUST declare required
Evidence types, collection methods or acceptable providers, freshness rules,
and retention policy.

**CP-FR-022 — Evidence provenance.** Evidence MUST identify the subject, method,
collector, tool or model version, input references, output references, time, and
integrity metadata. Evidence MUST distinguish mechanical, model-assisted, and
human sources.

**CP-FR-023 — Independent verdict.** A required Verdict MUST be issued by a
Verifier that satisfies the Unit's declared Independence Policy. Producer
self-assertion MUST NOT satisfy an independent gate.

**CP-FR-024 — Portable outcomes.** The core MUST represent at least `confirmed`,
`needs_fix`, `needs_human_review`, and `rejected`. Domain Packs MAY add details
but MUST map their terminal gate decision to a portable outcome.

**CP-FR-025 — Transition enforcement.** A Unit MUST NOT satisfy a downstream
dependency until all required gates have accepted it. An authorized override
MUST create a new Verdict recording actor, rationale, scope, expiry, and the
known failed or absent evidence.

**CP-FR-026 — Evidence expiry and invalidation.** Policy MUST be able to expire or
invalidate evidence when its subject, method, capability version, environment,
or relevant directive changes.

### 6.5 Human steering

**CP-FR-027 — Scoped Directive.** A Director MUST be able to issue a Directive
scoped to a run, stage, Unit selection, Unit, artifact, or domain-defined target.
The event MUST include actor, content, creation time, precedence, and status.

**CP-FR-028 — Directive resolution.** Before dispatch, the scheduler MUST resolve
all applicable active Directives into the Unit contract in a deterministic
precedence order.

**CP-FR-029 — Precise invalidation.** When a Directive changes, the interpreter
MUST compute and record the affected Unit set. Unrelated confirmed Units MUST
NOT be invalidated merely for implementation convenience unless the runtime
declares a coarser resumption level.

**CP-FR-030 — Steering, approval, and override distinction.** Implementations
MUST represent these as different event types and MUST NOT infer authority from
creative steering text.

### 6.6 Ledger and observability

**CP-FR-031 — Append-only events.** The portable run history MUST be expressible
as an ordered, append-only event stream covering compilation, dispatch,
attempts, claims, evidence, verdicts, directives, approvals, invalidations,
cancellation, and completion.

**CP-FR-032 — Replay.** A conforming implementation MUST reconstruct portable
run and Unit state from the accepted event stream plus referenced immutable
objects.

**CP-FR-033 — Correlation.** Run, contract, plan, Unit, attempt, claim, evidence,
verdict, directive, approval, capability, and adapter identifiers MUST be
correlatable.

**CP-FR-034 — Inspection.** Operators MUST be able to inspect the effective
contract, current state, ready and blocked Units, open approvals, active
Directives, evidence gaps, budget usage, and capability provenance without
reading model-private reasoning.

**CP-FR-035 — Redaction.** Portable events and exports MUST support field-level
redaction and references to protected payloads. Secrets MUST NOT be required in
the ledger to reproduce control decisions.

### 6.7 Capability lifecycle

**CP-FR-036 — Gap classification.** A missing capability MUST be classified as
agent judgment, deterministic local tool, shared/core capability, or privileged
integration before a candidate implementation is registered.

**CP-FR-037 — Capability manifest.** A capability MUST declare purpose, version,
schemas, permissions, side effects, dependencies, determinism expectations,
self-test, artifact contract, and provenance.

**CP-FR-038 — Local-first trust.** A newly authored capability MUST begin at a
non-shared trust tier. Registration MUST NOT imply promotion.

**CP-FR-039 — Promotion gates.** Policy MUST be able to require sandboxed
self-tests, static analysis, representative runs, success thresholds,
independent audit, signature, human approval, canary activation, and rollback
criteria.

**CP-FR-040 — Rejection and rollback.** Rejected, compromised, or regressed
capability versions MUST be revocable. Existing run provenance MUST retain the
fact that the version was used even after revocation.

**CP-FR-041 — External contribution boundary.** Generation of a proposal packet
MUST be separable from mutation of a source repository, package registry, or
external service. Proposal generation MUST NOT imply authorization to publish.

### 6.8 Memory classes

**CP-FR-042 — Typed memory class.** Implementations MUST distinguish episodic,
working, policy, preference/taste, and capability memory when those classes are
enabled.

**CP-FR-043 — Memory authority.** Each memory class MUST declare readers,
writers, scope, retention, provenance, conflict resolution, and invalidation.

**CP-FR-044 — No silent promotion.** Model-generated summaries or observations
MUST NOT become policy or shared capability memory without the required
promotion event.

### 6.9 Conformance and portability

**CP-FR-045 — Version declaration.** Implementations, Domain Packs, adapters,
and exports MUST declare the ContractPlane specification version they target.

**CP-FR-046 — Unknown-field behavior.** The specification MUST define which
unknown fields are ignored, preserved, warned, or rejected. Security-relevant
unknown authority and policy fields MUST fail closed.

**CP-FR-047 — Conformance suite.** The project MUST publish fixtures for contract
compilation, event replay, unit invalidation, gate enforcement, steering,
approval, adapter negotiation, and capability promotion.

**CP-FR-048 — Conformance claims.** An implementation MUST identify the suite
version, profile, and results behind any compatibility claim.

## 7. Non-functional requirements

### 7.1 Portability

- Core serialized objects SHOULD use JSON-compatible types and published JSON
  Schemas.
- Human-authored representations MAY use YAML or another format, but canonical
  serialization MUST be unambiguous.
- Domain Packs MUST separate portable semantics from adapter-specific extension
  blocks.

### 7.2 Security

- Deny-by-default MUST apply to authority not explicitly granted.
- Untrusted Domain Packs and capabilities MUST be inspectable before execution.
- Secret values MUST be resolved at the latest practical boundary and MUST NOT
  be placed into prompts, logs, or evidence by default.
- Failure to evaluate a security gate MUST fail closed.
- See [../../SECURITY.md](../../SECURITY.md).

### 7.3 Reliability

- Portable state transitions MUST be idempotent under duplicate event delivery.
- Distributed implementations MUST define lease, fencing, and duplicate-attempt
  behavior.
- A crash after an external effect but before acknowledgment MUST result in an
  `effect_unknown`-equivalent failure detail, not an automatic safe retry.

### 7.4 Auditability

- An auditor SHOULD be able to answer who requested, compiled, approved,
  executed, verified, overrode, promoted, and cancelled an action.
- Retained evidence SHOULD be content-addressed or tamper-evident according to
  the threat model.
- Audit export MUST exclude model-private chain-of-thought and secrets.

### 7.5 Privacy

- Data classification and retention MUST be expressible per contract and
  evidence type.
- Domain Packs SHOULD request the minimum data necessary for each Unit.
- Deletion requirements MUST distinguish removal of protected payloads from
  retention of non-sensitive integrity and audit metadata.

### 7.6 Performance

- The contract plane SHOULD add bounded overhead relative to the underlying
  work and SHOULD permit streaming of progress events.
- Evidence collection SHOULD use deterministic low-cost checks before invoking
  expensive model or human review.
- The scheduler SHOULD expose concurrency and budget backpressure.

### 7.7 Usability

- Users SHOULD invoke an outcome-oriented public entrypoint rather than an
  internal worker role.
- Approval prompts MUST state the concrete effect and scope in user language.
- Operator views SHOULD distinguish pending work, worker claims, verified work,
  and blocked gates.

### 7.8 Extensibility

- Extensions MUST be namespaced.
- Portable core semantics MUST NOT depend on one vendor extension.
- An implementation MUST preserve unknown non-security extension data during a
  lossless read/write round trip when the profile requires it.

### 7.9 Offline operation

- A minimal profile SHOULD support local execution without a hosted control
  plane.
- Offline operation MUST NOT weaken declared evidence or authority policy; it
  must report unsupported gates instead.

## 8. Safety invariants

The following invariants are non-negotiable for the core profile:

1. No required gate is satisfied by a producer claim alone.
2. No delegation expands authority without a recorded grant.
3. No material contract change silently reuses a semantically invalid Unit.
4. No steering text is interpreted as an approval or secret grant.
5. No local capability becomes shared merely because it executed once.
6. No unknown effect is reported as safely rolled back or safely retryable.
7. No compatibility claim is made solely from a shared acronym or object name.
8. No replay requires secret values or private model reasoning to determine the
   portable control state.

## 9. Initial acceptance scenarios

The first reference implementation and conformance fixtures SHOULD cover:

1. **Parallel media units:** dynamic fan-out, independent mechanical and
   editorial evidence, human candidate selection, and partial invalidation.
2. **Scoped correction:** a Directive changes one selected artifact and only its
   downstream Units rerun.
3. **Missing tool:** a deterministic capability remains local, fails promotion
   without a valid self-test, then passes audit and canary before sharing.
4. **Permission denial:** an adapter refuses network access not present in the
   Authority Envelope and emits a portable failure.
5. **Crash and resume:** the interpreter rebuilds state from the ledger and does
   not rerun confirmed Units.
6. **Unknown external effect:** a crash around publication blocks automatic
   retry until effect reconciliation.
7. **Runtime substitution:** the same portable contract runs through two
   adapters with equivalent observable state transitions.
8. **Non-media validation:** a second Domain Pack demonstrates that the core
   abstractions are not specific to video processing.

## 10. Traceability

The Proposed, currently non-normative core model is in
[../../rfds/0001-core-model.md](../../rfds/0001-core-model.md). Component
responsibilities and sequences are in [architecture.md](architecture.md).
Security controls are expanded in [../../SECURITY.md](../../SECURITY.md).
