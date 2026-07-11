# ContractPlane Status

Last reviewed: 2026-07-11

Release: `0.1.0a1` (alpha)

Project stage: alpha design and reference kernel

Distribution: GitHub prerelease. PyPI publication is pending a project-scoped
Trusted Publisher for `Q00/contractplane`.

## Publication status

ContractPlane is not production-ready and does not yet implement the complete
Agent Contract Plane described in the whitepaper and design documents.

- The `contractplane.dev/v1alpha1` **DomainPack schema is an alpha candidate**.
  It is strict and test-backed, but may change before acceptance through project
  governance.
- [RFD 0001](rfds/0001-core-model.md) is **Proposed**. Its Execution Contract,
  Verdict, Directive, authority, memory, and capability-lifecycle semantics are
  target architecture, not a claim about current runtime behavior.
- The event-sourced Python state machine is an **experimental kernel profile**:
  `contractplane.dev/kernel-state/v0alpha1`. It is not a stable public
  conformance contract.

In short: RFD 0001 is Proposed and non-normative.

## Implemented in `v0.1.0a1`

### DomainPack authoring and validation

- YAML/JSON loading through safe YAML parsing;
- strict JSON Schema structure with unknown-field rejection;
- semantic reference validation for capabilities, roles, evidence, policies,
  flows, stages, and entrypoints;
- embedded JSON Schema validation;
- agent capability/role binding validation;
- evidence-required policy checks;
- `singleton` and `each` fan-out declaration validation;
- dependency-cycle detection;
- rejection of obvious shell syntax in declarative `when` strings.

### Deterministic plan compilation

- explicit flow or entrypoint selection;
- deterministic maximal topological waves;
- compiled capability, role, binding, permission, schema, policy, and evidence
  declarations;
- stable JSON serialization and SHA-256 plan digest;
- checked-in compiler golden fixtures, including an OpenClip flow.

The compiler emits an `ExecutionPlan`, not a fully resolved Execution Contract.
It does not consume an Intent or Environment Snapshot.

### Experimental local transition kernel

- append-only local JSONL ledger with contiguous sequence validation;
- plan-digest binding and replay;
- singleton unit materialization;
- caller-managed registration and sealing of `each` fan-out units;
- per-unit attempts and bounded retry;
- capability output-schema validation for producer claims;
- caller-supplied evidence receipts, including JSON Schema validation where the
  evidence definition provides a schema;
- simple always/never pre-dispatch authorization gating;
- condition skip recording when an adapter has evaluated the condition;
- cancellation and local state snapshots.

This kernel manages state transitions. It does not execute capability bindings.

### Tooling and publication fixtures

- `validate`, `inspect`, `compile`, and `schema` CLI commands;
- Python 3.11+ package and wheel;
- schema/compiler/state unit tests and a small conformance corpus;
- static project site and canonical `contractplane.dev` namespace;
- OpenClip DomainPack as a substantial compilation fixture.

## Not implemented

The following target capabilities are not present in `v0.1.0a1`:

- natural-language intent routing or Domain Pack discovery;
- Intent, Environment Snapshot, or resolved Execution Contract objects;
- fan-out selector evaluation;
- `when` condition evaluation;
- runtime, agent, tool, MCP, A2A, Agent Client Protocol, or Mastra adapters;
- invocation of capability bindings;
- filesystem, process, network, secret, spending, or external-mutation authority
  enforcement;
- budget enforcement beyond per-unit attempt count;
- typed Attempt, Claim, EvidenceRecord, or Verdict objects from RFD 0001;
- verifier identity or independence enforcement;
- evidence freshness, integrity, provenance, or collector policy;
- scoped Directive processing and semantic invalidation;
- confirmed-unit reuse across contract revisions;
- suspension/resumption around external systems;
- distributed leases, fencing, event delivery, or reconciliation;
- typed memory classes;
- capability discovery, sandboxed trial, audit, canary, promotion, rollback, or
  revocation;
- a conforming OpenClip execution adapter;
- cross-runtime conformance results;
- production security hardening or audit.

## What the current evidence gate proves

The current state kernel proves only that:

1. a claim matches its declared capability output schema;
2. every required evidence identifier received one caller-supplied receipt
   marked accepted;
3. a receipt matches an evidence JSON Schema when one is present; and
4. an `always` approval policy received a caller-supplied pre-dispatch decision
   with a non-empty actor string.

It does **not** prove that the evidence collector is independent, that a semantic
review actually occurred, that an external receipt is authentic, that the actor
was authenticated, or that the underlying artifact is correct. Those are target
requirements for future profiles.

## Stability table

| Surface | Identifier | Status | Compatibility promise |
|---|---|---|---|
| DomainPack schema | `contractplane.dev/v1alpha1` | Alpha candidate | May change with migration notes |
| Compiler output | `contractplane.dev/plan/v1alpha1` | Experimental | Golden-tested within `0.1.x`; not stable cross-runtime contract |
| Kernel state behavior | `contractplane.dev/kernel-state/v0alpha1` | Experimental | No persistence or compatibility promise yet |
| RFD 0001 core model | Proposed RFD | Design target | Non-normative until accepted |
| OpenClip DomainPack | Fixture | Compile-only | No ContractPlane execution adapter yet |
| Runtime adapters | None | Not implemented | None |

## Release claim checklist

Before a release or website claims a target feature, it should have:

- accepted normative language or an explicitly named experimental profile;
- a machine-readable schema where applicable;
- reference implementation behavior;
- positive and adversarial tests;
- conformance fixtures;
- security limitations and adapter enforcement documented;
- migration guidance from prior published profiles.

## Verification

The repository CI is expected to validate the candidate schema, compiler golden
files, OpenClip compilation fixture, local documentation links and publication
language, Python 3.11 compatibility, and installation from a built wheel.
