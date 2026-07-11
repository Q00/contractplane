# RFD 0001: ContractPlane Core Model

| Field | Value |
|---|---|
| Status | Proposed |
| Authors | ContractPlane maintainers |
| Created | 2026-07-11 |
| Target | Future accepted core profiles; informs but does not define the current DomainPack alpha candidate |
| Discussion | Repository review process |

> **Status boundary:** This RFD is Proposed and non-normative. The current
> `contractplane.dev/v1alpha1` DomainPack schema is an alpha candidate, not an
> implicit acceptance of this RFD. The current event-sourced state machine is an
> experimental `contractplane.dev/kernel-state/v0alpha1` profile and does not
> implement the portable state and event model below. See [../STATUS.md](../STATUS.md).

## 1. Summary

This RFD proposes the portable core model for ContractPlane, whose formal
architecture is the **Agent Contract Plane**.

The model begins with one compilation relation:

```text
Intent + Domain Pack + Environment -> Execution Contract
```

The resulting contract governs one run through the following acceptance chain:

```text
Plan -> Unit -> Claim -> Evidence -> Verdict -> Transition
```

The proposal defines object identities, revisions, portable states, events,
authority, evidence, human control, capability trust, adapter boundaries, and
minimum conformance behavior.

## 2. Motivation

Agent and workflow runtimes can execute work but do not, by themselves, provide
a portable answer to:

- which domain procedure applies;
- which authority each piece of work may exercise;
- how work fans out and resumes by semantic unit;
- what proves a result acceptable;
- how verifier independence is defined;
- how human guidance affects only relevant work;
- how a locally created capability earns shared trust;
- how these semantics survive runtime substitution.

OpenClip demonstrated a useful pattern in one domain: one public entrypoint,
private worker roles, manifest-declared stages, per-unit fan-out, structured
worker output, independent verification, scoped steering, keyed resumption, and
audited tool promotion. This RFD generalizes that pattern and removes
video-specific and single-machine assumptions.

## 3. Scope

This RFD specifies:

- the conceptual and serialized core objects;
- identity and revision rules;
- plan and unit execution semantics;
- claim, evidence, verdict, and gate semantics;
- human Directive, Approval, and Override semantics;
- authority and budget envelopes;
- capability lifecycle states;
- portable ledger events and reducers;
- adapter declarations and compatibility;
- minimum conformance requirements.

It does not specify a model API, storage engine, scheduler implementation, UI,
hosted service, or transport wire format.

## 4. Protocol naming

The product name is ContractPlane. The architecture name is Agent Contract
Plane. [`contractplane.dev`](https://contractplane.dev/) is the canonical project
and specification namespace. The bare acronym `ACP` is intentionally avoided in
machine identifiers.

This model is not:

- Agent Client Protocol, the editor/IDE-to-coding-agent protocol; or
- the IBM/BeeAI-origin Agent Communication Protocol, whose project documentation
  states it is now part of A2A under the Linux Foundation.

Those systems may be used through adapters. They do not share this object or
state model unless an explicit adapter specification says so.

## 5. Design principles

1. **Portable semantics, replaceable runtime.**
2. **Immutable contracts and append-only corrections.**
3. **Least authority at Unit granularity.**
4. **Claim is not confirmation.**
5. **Independent gates before downstream consumption.**
6. **Human steering is scoped and replayable.**
7. **Stable Unit identity enables minimal invalidation and resume.**
8. **Capability registration is not capability promotion.**
9. **Unsupported security semantics fail closed.**
10. **Model-private reasoning is not required for replay.**

## 6. Terminology

### 6.1 Director

The human or authorized group accountable for reserved decisions. A Director can
issue Directives, grant or deny Approval, and, when policy permits, issue an
Override.

### 6.2 Intent

A typed statement of requested outcome, supplied inputs, explicit constraints,
actor, and user-visible success conditions. Intent includes original request
provenance but does not grant authority.

### 6.3 Domain Pack

A versioned bundle of domain semantics: metadata, entrypoints, roles,
capabilities, flows, policies, evidence definitions, and schemas.

The current `v1alpha1` alpha-candidate DomainPack schema already represents:

- `Capability` kinds `deterministic`, `agent`, and `integration`;
- side effects `none`, `local`, and `external`;
- `Role` instructions and capability access;
- Evidence kinds `json-schema`, `artifact`, `semantic-review`, and
  `external-receipt`;
- policies with evidence, approval, and attempt settings;
- flows, stages, dependencies, `singleton` or `each` fan-out, and entrypoints.

This RFD defines the broader target semantics around that initial subset.

### 6.4 Environment Snapshot

An immutable observation of available adapters, capability versions, platform
constraints, storage features, policy overlays, budgets, and grants used during
compilation. Secret values are not part of the snapshot.

### 6.5 Execution Contract

An immutable resolved agreement for one Run revision. It binds Intent, Domain
Pack version, Environment Snapshot, policy, selected flow, adapter requirements,
authority, budgets, evidence, human checkpoints, and failure semantics.

### 6.6 Execution Plan

The dependency graph instantiated from an Execution Contract. The existing
`v1alpha1` reference compiler emits an `ExecutionPlan` containing topological
waves of compiled stages and a deterministic digest. In the complete model, the
Execution Plan is a component of an Execution Contract rather than a substitute
for it.

### 6.7 Stage

A named logical operation in a Domain Pack flow. A Stage becomes one or more
Units when the Plan is instantiated or dynamically expanded.

### 6.8 Unit

The smallest independently dispatchable, retryable, resumable, and verifiable
piece of work. A Unit carries resolved input, capability, role, authority,
budget, policy, directives, evidence obligations, and acceptance gates.

### 6.9 Attempt

One execution of one Unit revision through a runtime adapter. Retries create new
Attempts; they do not overwrite prior Attempt history.

### 6.10 Claim

The producer's structured assertion that an Attempt produced specified outputs
and met stated conditions. A Claim is not an accepted completion state.

### 6.11 Evidence

An observable record supporting or refuting a Claim. Evidence binds to a subject
and records method, collector, version, input and output references, time,
integrity, and evidence class.

### 6.12 Verdict

A gate decision issued under a Verifier and Independence Policy. A Verdict maps
to a portable outcome and records findings and remediation.

### 6.13 Directive

A scoped human instruction that changes desired behavior. It does not grant
authority.

### 6.14 Approval

An authenticated decision granting or denying a concrete requested action or
authority for a stated scope and time.

### 6.15 Override

An authorized decision to accept known missing or failing evidence or policy
risk. It creates a new Verdict-like record and never erases the original
failure.

### 6.16 Capability

A versioned implementation that can perform a declared operation through an
adapter. It includes schemas, permissions, side effects, provenance, trust
state, and lifecycle evidence.

### 6.17 Ledger

The ordered append-only event stream from which portable Run and Unit control
state can be reconstructed.

## 7. Core object model

The following fields are semantic requirements, not the final JSON Schema.

### 7.1 Intent

```text
Intent {
  id
  actor
  outcome
  inputs
  constraints
  success_conditions
  locale?
  provenance
  created_at
}
```

`inputs` may contain protected object references. Intent text cannot directly
set host policy or grants.

### 7.2 DomainPackVersion

```text
DomainPackVersion {
  api_version
  name
  version
  digest
  source
  entrypoints[]
  roles[]
  capabilities[]
  evidence_definitions[]
  policies[]
  flows[]
  compatibility
  signatures[]?
  revocation?
}
```

Domain Pack versions are immutable. Mutable tags may resolve to a version before
compilation but must not appear as the only provenance in a contract.

### 7.3 EnvironmentSnapshot

```text
EnvironmentSnapshot {
  id
  observed_at
  platform
  adapters[]
  capabilities[]
  storage_features
  sandbox_features
  policy_overlays[]
  grants[]
  budgets
  secret_references[]
  digest
}
```

Availability and authority are distinct fields. A discovered credential does
not create a grant.

### 7.4 ExecutionContractRevision

```text
ExecutionContractRevision {
  id
  run_id
  revision
  spec_profile
  compiler_version
  intent_ref
  domain_pack_ref
  environment_ref
  policy_refs[]
  plan_ref
  authority
  budgets
  evidence_policy
  human_control_policy
  memory_bindings[]
  adapter_requirements
  failure_policy
  retention_policy
  parent_revision?
  invalidation_summary?
  digest
  created_at
}
```

The contract is immutable. Modification creates a new revision.

### 7.5 PlanRevision

```text
PlanRevision {
  id
  contract_ref
  revision
  nodes[]
  edges[]
  initial_waves[]
  dynamic_expansion_rules[]
  digest
}
```

Nodes reference Stage semantics. Units may be materialized lazily when dynamic
fan-out inputs become confirmed.

### 7.6 UnitRevision

```text
UnitRevision {
  id
  logical_unit_id
  unit_key
  plan_ref
  node_id
  revision
  normalized_input
  dependencies[]
  capability_ref
  role_ref?
  adapter_requirements
  authority
  budget
  effective_directives[]
  expected_output_schema
  evidence_requirements[]
  acceptance_policy
  retry_policy
  timeout_policy
}
```

The `unit_key` covers every non-secret semantic input that can change accepted
output. If an implementation cannot calculate a stable key, it must not claim
portable Unit reuse.

### 7.7 Attempt

```text
Attempt {
  id
  unit_ref
  ordinal
  adapter_ref
  worker_identity
  lease_or_fence?
  started_at
  ended_at?
  status
  failure?
  usage?
}
```

Attempt status does not directly determine Unit acceptance.

### 7.8 Claim

```text
Claim {
  id
  unit_ref
  attempt_ref
  producer
  outputs[]
  claimed_conditions[]
  capability_versions[]
  adapter_version
  created_at
  signature?
}
```

Output references should include type, schema, digest or integrity metadata, and
storage location as policy permits.

### 7.9 EvidenceRecord

```text
EvidenceRecord {
  id
  subject_ref
  claim_ref?
  requirement_id
  class
  method
  collector
  collector_version
  observed_inputs[]
  observations
  artifact_refs[]
  result
  collected_at
  valid_until?
  environment_constraints?
  integrity?
  redaction?
}
```

Portable classes initially include `mechanical`, `model_assisted`, and `human`.
Domain Pack evidence kinds map to one of these classes.

### 7.10 Verdict

```text
Verdict {
  id
  unit_ref
  claim_ref
  verifier
  independence_policy
  evidence_refs[]
  outcome
  findings[]
  required_fix?
  confidence?
  policy_version
  created_at
  override_ref?
}
```

Portable outcomes are:

- `confirmed`;
- `needs_fix`;
- `needs_human_review`;
- `rejected`.

Confidence cannot turn a non-confirmed outcome into confirmation.

### 7.11 Directive

```text
Directive {
  id
  run_id
  actor
  scope
  content
  precedence
  status
  created_at
  expires_at?
  supersedes?
  resolved_at?
  resolution?
}
```

Portable status includes `active`, `resolved`, `superseded`, `expired`, and
`withdrawn`.

### 7.12 ApprovalRequest and ApprovalDecision

```text
ApprovalRequest {
  id
  contract_ref
  unit_ref?
  requested_action
  requested_authority
  target
  material_arguments_or_redacted_summary
  requester
  created_at
  expires_at
}

ApprovalDecision {
  id
  request_ref
  actor
  decision
  scope
  rationale?
  created_at
  expires_at?
}
```

Portable decisions are `approved`, `denied`, and `expired`. A change to material
arguments creates a new request.

### 7.13 CapabilityVersion

```text
CapabilityVersion {
  id
  version
  kind
  description
  input_schema
  output_schema
  permissions
  side_effects
  binding
  dependencies[]
  self_test
  provenance
  trust_state
  reliability_evidence[]
  reviews[]
  signatures[]?
  revocation?
}
```

## 8. Identity and revision rules

1. Run identity remains stable across contract revisions.
2. Contract, Plan, Unit, Capability, Claim, Evidence, Verdict, Directive, and
   Approval records are immutable versions or events.
3. Correction appends a superseding object or event.
4. An Attempt belongs to exactly one Unit revision.
5. A Claim belongs to exactly one Attempt.
6. Evidence may evaluate more than one subject only when its method and schema
   explicitly support a set; otherwise it binds to one subject.
7. A Verdict belongs to one Unit revision and Claim.
8. A Unit can become confirmed only through an accepted Verdict.
9. Reusing a confirmed Unit requires the same Unit key and still-valid Evidence
   and policy.
10. Secret values are never used directly as portable identifiers.

## 9. Compilation semantics

The compiler performs:

1. Intent normalization and schema validation.
2. Domain Pack discovery and explicit version selection.
3. Environment Snapshot validation.
4. EntryPoint and flow resolution.
5. Capability and adapter compatibility resolution.
6. Policy overlay and precedence evaluation.
7. Authority and budget calculation.
8. Evidence, independence, and human checkpoint binding.
9. Plan graph validation and digest calculation.
10. Contract emission or typed diagnostics.

Compilation must complete before effectful dispatch. Model-assisted routing may
propose a choice, but the selected pack and flow are explicit in compiler input
or output and are not hidden in model reasoning.

Given canonical equivalent inputs, compiler outputs must be semantically
equivalent. Non-semantic metadata such as generation timestamp may differ and
must not affect the semantic digest.

## 10. Plan and wave semantics

A Plan is a directed graph. The core profile requires acyclic dependency graphs;
looping behavior, if later standardized, must be represented as bounded
expansion or a profile extension.

A ready Unit satisfies all of the following:

- every dependency has an accepted output;
- required inputs have resolved;
- applicable Directives have been compiled into the Unit revision;
- required Approval exists and is valid;
- adapter and capability remain eligible;
- authority and budget remain available;
- the Unit is not cancelled, blocked, or already validly confirmed.

A wave is the maximal or policy-bounded set of ready Units selected for
concurrent dispatch. Implementations may dispatch fewer Units due to resource
limits but must not violate dependencies.

Dynamic fan-out materializes Units from accepted prior output. The expansion
rule, source output, ordering, and resulting Unit keys are recorded.

## 11. Unit state machine

The proposed portable Unit states are:

```text
planned
ready
running
claimed
verifying
confirmed
needs_fix
needs_human_review
rejected
failed
suspended
cancelled
invalidated
```

Required transitions:

```text
planned -> ready
ready -> running | suspended | cancelled
running -> claimed | failed | suspended | cancelled
claimed -> verifying
verifying -> confirmed | needs_fix | needs_human_review | rejected
needs_fix -> ready | cancelled
needs_human_review -> suspended
suspended -> ready | running | rejected | cancelled
failed -> ready | rejected | cancelled
confirmed -> invalidated
invalidated -> ready | cancelled
```

Implementations may add internal states but must preserve the distinction
between `claimed` and `confirmed`.

## 12. Run state machine

The proposed portable Run states are:

```text
created
compiling
ready
running
suspended
cancelling
cancelled
completed
failed
rejected
```

A Run is `completed` only when all required deliverables and terminal gates in
the active contract revision are confirmed or explicitly satisfied by an
authorized Override.

## 13. Event model

The proposed portable ledger uses typed append-only events. Its initial event
vocabulary should include:

| Event | Meaning |
|---|---|
| `intent.accepted` | Intent entered the contract plane |
| `domain-pack.selected` | explicit pack version bound |
| `environment.observed` | Environment Snapshot bound |
| `contract.compiled` | immutable contract revision created |
| `contract.rejected` | compilation failed with diagnostics |
| `plan.created` | Plan revision created |
| `plan.expanded` | dynamic Units materialized |
| `unit.ready` | Unit dependencies and policy satisfied |
| `unit.dispatched` | Attempt handed to an adapter |
| `unit.progressed` | non-state-bearing progress reported |
| `unit.failed` | Attempt failed |
| `claim.recorded` | producer Claim recorded |
| `evidence.recorded` | Evidence recorded |
| `verdict.issued` | gate decision recorded |
| `unit.confirmed` | accepted Verdict applied |
| `unit.invalidated` | prior accepted result became stale |
| `directive.added` | scoped steering added |
| `directive.resolved` | steering handled or closed |
| `approval.requested` | authority or effect decision requested |
| `approval.decided` | approval, denial, or expiry recorded |
| `override.issued` | authorized risk acceptance recorded |
| `run.suspended` | no progress until external input or policy change |
| `run.cancel.requested` | cancellation requested |
| `run.cancelled` | portable cancellation outcome established |
| `run.completed` | active contract completion established |
| `capability.registered` | local candidate registered |
| `capability.tested` | lifecycle Evidence added |
| `capability.reviewed` | independent review recorded |
| `capability.promoted` | trust tier increased |
| `capability.revoked` | version made ineligible for new selection |

Each event includes event ID, type, schema version, Run or registry scope,
subject references, actor, timestamp, causal references, and a payload or
protected payload reference.

Reducers must be idempotent under duplicate event delivery. Security-sensitive
transitions must validate current revision and actor authority rather than rely
only on event order.

## 14. Claim, Evidence, and Verdict semantics

### 14.1 Claim is non-terminal

A producer can report only what it claims to have done. Recording a Claim moves
the Unit to `claimed`, never directly to `confirmed`.

### 14.2 Evidence classes

- **Mechanical**: deterministic observation such as schema validation, checksum,
  probe, test, or external receipt validation.
- **Model-assisted**: rubric-bound observation created using a model. Provenance
  and inputs are required.
- **Human**: authenticated human judgment, approval, or observation.

Domain-specific kinds such as `artifact` or `semantic-review` map to one class.

### 14.3 Independence Policy

An Evidence requirement or Verdict defines acceptable separation between
producer and verifier. Levels may include:

- `self`: allowed only for non-gating diagnostic checks;
- `process`: separate role or process;
- `model`: distinct model or configuration;
- `organizational`: independent team or service;
- `human`: authenticated human reviewer;
- `combined`: a stated composition.

The exact serialized levels remain to be finalized. A gate must not claim a
stronger level than the deployment can establish.

### 14.4 Gate evaluation

A Verdict is accepted only if:

- it evaluates the current Unit revision and Claim;
- all required Evidence is present, valid, fresh, and correctly bound;
- the verifier satisfies Independence Policy;
- policy accepts the outcome;
- no later revocation or invalidation applies.

Evidence collection failure and verifier timeout are not confirmation.

## 15. Human control semantics

Directive, Approval, and Override are distinct.

### 15.1 Directive

A Directive changes the desired execution. Scopes include Run, Stage, Unit
selector, Unit, Artifact, and domain extension. Directive precedence is
explicit. A Directive participates in Unit identity when it can change output.

Adding, superseding, withdrawing, or expiring a Directive triggers an
invalidation analysis. Only affected Units and downstream consumers are
semantically invalidated.

### 15.2 Approval

Approval grants or denies one requested effect or authority. It binds to
material arguments, target, contract revision, actor, scope, and expiry. A
changed action requires a new request.

### 15.3 Override

Override records conscious acceptance of a known contract exception. Policy may
forbid override for immutable safety rules. The record includes the failed or
missing Evidence, actor authority, rationale, scope, and expiry.

## 16. Authority and budget semantics

The Authority Envelope is deny-by-default. Core categories are:

- filesystem read;
- filesystem write;
- process execution;
- network access;
- secret access;
- monetary or token spend;
- external mutation;
- delegation;
- memory read/write;
- evidence collection and verdict issuance.

Each category supports constraints such as paths, destinations, executable
identities, secret references, amounts, operation classes, and expiry.

Effective Unit authority is the intersection of host policy, organization
policy, Director grants, contract policy, adapter capability, and parent
authority. Delegation never computes a union that widens authority.

Budgets include attempts, wall time, tokens, cost, CPU, memory, storage,
concurrency, and network use. Budget breach produces a typed failure or
suspension according to policy; it does not invite an unbounded agent retry.

## 17. Capability lifecycle

Portable trust states are proposed as:

```text
discovered
local
trial
audited
shared
deprecated
retired
rejected
revoked
```

Allowed progression is policy-defined but must preserve these invariants:

1. Discovery or registration does not imply shared trust.
2. The author alone cannot satisfy an independent audit requirement.
3. Promotion Evidence is bound to an immutable capability version.
4. Publication is separate from proposal generation.
5. Revocation prevents new selection but preserves historical provenance.
6. Rollback selects a prior eligible version through a recorded policy event.

Promotion policy may require a manifest, self-test, sandbox, structured output,
static and dependency analysis, representative runs, success threshold,
independent review, signature, canary, and human approval.

## 18. Memory semantics

The core recognizes five memory classes:

- `episodic`;
- `working`;
- `policy`;
- `preference`;
- `capability`.

A memory binding declares store, scope, readers, writers, schema, retention,
provenance, and invalidation. Model-generated observations may write episodic or
working memory under policy. They cannot silently write policy or shared
capability memory.

Memory is optional for a Unit unless declared. An adapter must not supply a full
conversation transcript merely because its native framework normally does so.

## 19. Adapter declaration

An adapter declaration includes:

```text
AdapterDeclaration {
  id
  version
  spec_profiles[]
  invocation_kinds[]
  streaming
  structured_output
  cancellation
  suspension
  resume
  durability
  delivery_semantics
  sandbox_features
  authority_features
  secret_behavior
  telemetry_features
  limitations[]
}
```

Compilation fails when a required security or control semantic is unsupported.
Non-security optional behavior may fall back only when the contract declares an
acceptable fallback.

## 20. Failure model

Portable failure details should distinguish:

- invalid input or schema;
- compilation incompatibility;
- missing capability or adapter;
- authority denied;
- approval denied or expired;
- budget exhausted;
- timeout;
- adapter failure;
- worker failure;
- invalid Claim;
- evidence missing, invalid, stale, or collection failed;
- verdict rejection;
- external effect unknown;
- cancellation requested but unconfirmed;
- capability revoked;
- ledger or integrity failure.

Failures state whether retry is safe, unsafe, or requires reconciliation. The
default for an unknown external effect is reconciliation required.

## 21. Serialization and evolution

- Canonical portable serialization uses JSON-compatible values.
- Normative schemas use JSON Schema Draft 2020-12 unless superseded by RFD.
- YAML may be a human-authoring format but is parsed into the canonical model.
- Object types include explicit `apiVersion` and `kind` or equivalent versioned
  discrimination.
- Unknown security semantics fail closed.
- Unknown annotation fields may be preserved according to profile.
- Semantic digests exclude permitted non-semantic metadata.
- Breaking stable changes require a new major API version or profile.

## 22. Conformance requirements

The first core suite must test:

1. deterministic Domain Pack validation and plan compilation;
2. topological wave formation and dynamic `each` expansion;
3. stable Unit keys;
4. Claim not transitioning directly to confirmed;
5. required Evidence and Independence Policy enforcement;
6. all portable Verdict outcomes;
7. scoped Directive resolution and minimal invalidation;
8. Approval binding and replay resistance;
9. authority narrowing across delegation;
10. duplicate event idempotency and state replay;
11. crash/resume with confirmed Unit reuse;
12. external effect unknown blocking automatic retry;
13. capability promotion, rejection, revocation, and rollback;
14. adapter incompatibility for unsupported required semantics;
15. redacted export without secret values or private reasoning.

## 23. Security and privacy impact

This RFD increases the amount of structured execution metadata. That improves
auditability but creates a high-value ledger. Implementations must protect actor
identity, artifact references, model inputs, evidence, directives, and approval
records. Data minimization, protected object references, retention, and
redaction are part of the contract.

The model reduces ambient authority and confused-deputy risk by binding
permissions per Unit, but adapters must enforce the envelope. A declarative
permission field without enforcement is not a security control.

See [../SECURITY.md](../SECURITY.md).

## 24. Compatibility and migration

The current reference implementation's `v1alpha1` DomainPack alpha candidate,
`ExecutionPlan`, and experimental kernel-state profile are a subset:

- Existing Domain Pack identifiers, capability kinds, side-effect classes,
  Evidence kinds, policies, flow dependencies, fan-out, entrypoints, and
  deterministic plan digest should be preserved where compatible.
- A future Execution Contract may wrap the existing Execution Plan rather than
  rename it.
- The Python kernel has internal Unit state, claims, evidence receipts, approval,
  and a local JSONL ledger, but these do not implement the typed portable
  objects, independence rules, Verdicts, Directives, or event vocabulary in this
  RFD. They require new versioned schemas and conformance fixtures.
- Alpha compatibility allows change, but migrations and fixture updates should
  accompany semantic changes.

No compatibility with Agent Client Protocol or Agent Communication Protocol is
implied. Adapters receive their own specifications and tests.

## 25. Alternatives considered

### 25.1 Build a full agent framework

Rejected as the core direction. Mature frameworks already provide model, tool,
workflow, memory, deployment, and observability primitives. ContractPlane gains
leverage by remaining above them.

### 25.2 Use workflow success as completion

Rejected. Workflow execution status does not prove domain acceptance, and it
does not enforce producer/verifier separation.

### 25.3 Treat eval scores as Evidence without a Claim model

Rejected. Evals are valuable but vary between offline quality measurement,
asynchronous monitoring, and blocking acceptance. The contract must state which
Evidence gates a transition.

### 25.4 Store human guidance only in conversation memory

Rejected. It prevents deterministic scope resolution, audit, and minimal
invalidation.

### 25.5 Allow tools to promote themselves after successful use

Rejected. One success does not establish safety, portability, non-duplication,
or reliability.

### 25.6 Redefine another wire protocol under the ACP acronym

Rejected. Existing protocols already use the acronym, and ContractPlane's value
is semantic governance rather than another transport.

## 26. Consequences

### Positive

- domain procedures become inspectable and portable;
- accepted completion has explicit proof semantics;
- users can steer precisely and auditably;
- retries and resume operate on stable semantic units;
- capability evolution gains trust stages and rollback;
- runtime frameworks remain replaceable;
- conformance can compare observable behavior.

### Costs

- more schemas, identifiers, and event records;
- evidence collection adds latency and storage;
- independence requirements may add model or human cost;
- precise invalidation requires dependency discipline;
- adapter authors must expose limitations honestly;
- security and capability promotion add friction by design.

## 27. Open questions

1. Which fields belong in the minimal core versus optional profiles?
2. What exact Independence Policy levels are portable and testable?
3. Should Verdict outcomes include a portable `expired` state or express expiry
   only through Evidence invalidation?
4. How should nested ContractPlane runs expose their internal Evidence to a
   parent without violating encapsulation?
5. What canonicalization scheme should semantic digests use?
6. What is the minimum distributed event ordering requirement?
7. How should privacy deletion interact with tamper-evident audit chains?
8. Which capability reliability statistics are portable across domains?
9. How should policy conflict diagnostics be standardized?
10. Which second Domain Pack best falsifies media-specific assumptions?

## 28. Implementation plan

1. Keep the existing Domain Pack and deterministic Execution Plan compiler as
   the first authoring and compilation slice.
2. Add schemas for Intent, Environment Snapshot, and Execution Contract.
3. Replace or evolve the experimental kernel-state model with accepted Unit,
   Attempt, Claim, and portable ledger schemas.
4. Evolve caller-supplied evidence receipts into mechanical Evidence,
   independent Verdict reduction, and accepted gate enforcement.
5. Add Directive, Approval, invalidation, cancellation, and resume fixtures.
6. Add capability lifecycle and security conformance fixtures.
7. Stabilize the extracted OpenClip-derived media Domain Pack and add a
   conforming execution adapter.
8. Validate a non-media Domain Pack.
9. Implement one framework adapter, with Mastra as a strong candidate.
10. Move this RFD from Proposed to Accepted through governance, and from
    Accepted to Final only after normative schemas and core conformance fixtures
    land.

## 29. Decision requested

Accept the compilation relation, core object vocabulary, Claim/Evidence/Verdict
gate, scoped human-control model, governed capability lifecycle, and portable
ledger as the architectural foundation of ContractPlane, subject to refinement
of serialized schemas through follow-up RFDs.
