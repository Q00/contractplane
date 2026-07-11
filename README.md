# ContractPlane

![A dark architectural plane crossed by precise lines of light, representing the Agent Contract Plane.](site/assets/contractplane-hero.webp)

**A portable contract layer for governable agent execution.**

Project home and canonical namespace: [contractplane.dev](https://contractplane.dev/)

ContractPlane is an early-stage open architecture for turning a human intent and
domain-specific operating knowledge into an explicit, inspectable execution
contract. The formal architecture is called the **Agent Contract Plane**. The
formula below describes the target architecture; the current `v0.1` release
implements only the alpha DomainPack/compiler slice and an experimental local
state-transition kernel. See [STATUS.md](STATUS.md).

```text
Intent + Domain Pack + Environment -> Execution Contract
```

The execution contract states what may run, how work is decomposed, which
authority and budgets apply, what evidence each result must carry, when a human
must be consulted, and what is required before the run may advance.

> **Naming note:** ContractPlane is not the
> [Agent Client Protocol](https://agentclientprotocol.com/get-started/introduction),
> which connects editors and coding agents. It is also not the IBM/BeeAI-origin
> [Agent Communication Protocol](https://agentcommunicationprotocol.dev/introduction/welcome),
> whose documentation says it is now part of A2A under the Linux Foundation.
> ContractPlane can use Agent Client Protocol, A2A, MCP, HTTP, or local process
> adapters underneath it; it does not replace those transports.

## Why ContractPlane?

Most agent frameworks are good at invoking models, tools, workflows, and other
agents. The harder production questions remain application-specific:

- Which domain procedure applies to this request?
- Which work can fan out, and what is the smallest retryable unit?
- What is the difference between a worker saying “done” and the system proving
  that the work is acceptable?
- Which action needs approval, and can a human redirect only the affected unit?
- When a run discovers a missing capability, how can that capability be tested,
  audited, promoted, and rolled back without turning one improvisation into
  shared infrastructure?
- How can the same operating contract run on more than one agent framework?

ContractPlane makes those concerns first-class. Its central rule is:

> A claim is not confirmation.

## Core model

```text
Human / Application
        |
        v
  Contract Interpreter
        |
        v
  Execution Contract
        |
        v
  Plan -> Units -> Claims -> Evidence -> Verdicts
        |                              |
        +------ steering / approval ---+
        |
        v
  Runtime and transport adapters
```

- **Domain Pack**: a versioned bundle of intents, roles, flows, capability
  declarations, evidence rules, and policies for one domain.
- **Execution Contract**: an immutable, resolved agreement for one run, compiled
  from the intent, selected Domain Pack, environment, and policy.
- **Plan**: the dependency graph created from the contract.
- **Unit**: the smallest independently dispatchable, retryable, resumable, and
  verifiable piece of work.
- **Claim**: a producer's structured assertion that a unit is complete.
- **Evidence**: observable facts and artifact references that support or refute a
  claim.
- **Verdict**: an independently issued gate decision. Only a policy-accepted
  verdict advances the unit.
- **Directive**: a scoped human steering event that can invalidate and rerun only
  the affected portion of a plan.
- **Capability lifecycle**: governed discovery, trial, audit, promotion, and
  rollback of reusable capabilities.

See [RFD 0001](rfds/0001-core-model.md) for the **Proposed**, non-normative core
model.

## Try the current alpha

The current reference implementation validates the `v1alpha1` **alpha candidate**
DomainPack schema, inspects pack topology, and compiles a selected flow into a
deterministic `ExecutionPlan`. A library-level, event-sourced state machine can
manually register work units, gate completion on caller-supplied evidence
receipts, require simple caller-supplied pre-dispatch authorization, retry units,
and replay its local JSONL ledger.

It does **not** evaluate fan-out selectors or `when` conditions, invoke capability
bindings, run agents or tools, resolve an `Environment`, enforce declared
permissions as effective authority, issue independent Verdict objects, process
scoped steering invalidation, or promote capabilities. Its experimental kernel
profile is `contractplane.dev/kernel-state/v0alpha1`; it is not a stable
conformance contract.

```bash
python -m pip install "contractplane==0.1.0a1"
git clone https://github.com/Q00/contractplane.git
cd contractplane

contractplane validate examples/hello-domain/domainpack.yaml
contractplane inspect examples/hello-domain/domainpack.yaml
contractplane compile examples/hello-domain/domainpack.yaml --entrypoint hello
contractplane schema --out /tmp/contractplane-domainpack.schema.json
```

The [hello-domain example](examples/hello-domain/domainpack.yaml) demonstrates
the current authoring surface: deterministic, agent, and integration
capabilities; local and external side effects; roles; evidence; approval policy;
dependency waves; conditional stages; and `each` fan-out.

## Model a general domain

Start with the operating contract, not with agent names.

1. Define one or more public **entrypoints** in outcome language.
2. Describe each required **capability** as deterministic, agentic, or an
   integration, including schemas, permissions, and side effects.
3. Add private **roles** only where judgment needs bounded instructions.
4. Declare the **evidence** that must exist before each result is accepted.
5. Encode retry and human-approval rules as **policies**.
6. Arrange stages into a dependency graph and choose the smallest meaningful
   `singleton` or `each` fan-out boundary.
7. Validate and compile the pack, then inspect its waves, declared permissions,
   side effects, evidence, and policies before implementing runtime bindings and
   real authority enforcement.

The same sequence applies to media production, incident response, research,
compliance review, customer support, and data operations. A domain whose success
cannot be observed should first improve its evidence contract rather than add
more agent autonomy.

## What makes it different

ContractPlane is not trying to out-feature full application frameworks.

**Mastra orchestrates agents; ContractPlane governs execution.** This is a
statement about architectural focus, not a claim that Mastra lacks governance
features. Mastra already provides typed agents and workflows, approvals,
snapshots, memory, observability, evals, and durable execution. ContractPlane
defines a portable contract above such runtimes: domain packaging,
proof-carrying execution, scoped steering, and governed capability evolution.

The intended relationship is complementary:

```text
ContractPlane: domain contract, authority, evidence, lifecycle, conformance
Runtime:       Mastra, Codex, Claude, LangGraph, custom scheduler
Transport:     Agent Client Protocol, A2A, MCP, HTTP, stdio, local CLI
```

## Target design principles

The principles below describe the proposed Agent Contract Plane. Features such
as independent Verdicts, steering invalidation, effective authority, canary
promotion, and rollback are not implemented by the `v0.1` reference kernel.

1. **Contracts before execution.** Resolve inputs, authority, budgets, gates, and
   adapter requirements before dispatching work.
2. **One public intent surface, private role graph.** Users ask for outcomes;
   the interpreter chooses internal roles and flows.
3. **Proof before progress.** Workers produce claims. Independent gates decide
   whether a unit may advance.
4. **Humans steer by scope.** A directive targets a run, stage, unit, or artifact
   and is retained as an auditable event.
5. **Determinism where possible, judgment where necessary.** Mechanical checks
   and agent judgment are distinct evidence classes.
6. **Resume by unit, not by wishful retry.** Confirmed units remain reusable
   unless their inputs, contract, or governing directive changes.
7. **Capabilities earn trust.** A locally useful tool does not become shared
   capability without tests, representative runs, independent review, and a
   rollback path.
8. **Adapters are replaceable.** A Domain Pack must not require one model vendor,
   agent framework, or transport unless it explicitly declares that constraint.
9. **Authority is explicit and least-privileged.** Network, filesystem, secrets,
   external mutation, and spending are separate grants.
10. **The ledger is part of the product.** Plans, steering, approvals, claims,
    evidence, verdicts, and promotions must be explainable after the run.

## Repository map

- [WHITEPAPER.md](WHITEPAPER.md): motivation, thesis, and architecture narrative
- [STATUS.md](STATUS.md): implemented surface, experimental profiles, and missing
  target capabilities
- [docs/design/requirements.md](docs/design/requirements.md): functional and
  non-functional requirements
- [docs/design/architecture.md](docs/design/architecture.md): component and
  runtime design
- [docs/design/mastra-comparison.md](docs/design/mastra-comparison.md): factual
  comparison and integration strategy
- [rfds/0001-core-model.md](rfds/0001-core-model.md): Proposed, currently
  non-normative core object and state model
- [SECURITY.md](SECURITY.md): threat model and secure execution requirements
- [GOVERNANCE.md](GOVERNANCE.md): decision process, compatibility, and project
  roles
- [`spec/v1alpha1/domainpack.schema.json`](spec/v1alpha1/domainpack.schema.json):
  current DomainPack alpha-candidate schema
- `domain-packs/`: portable domain packages
- `adapters/`: runtime and transport integrations
- `conformance/`: implementation-neutral compatibility fixtures

## A conceptual run

The following is a target-architecture illustration, not a flow the `v0.1`
kernel can execute. Machine-readable candidate schemas belong in `spec/`.

```text
1. Accept intent: “Turn these recordings into three publishable clips.”
2. Discover a compatible media Domain Pack.
3. Inspect the environment: available tools, permissions, budget, and storage.
4. Compile an Execution Contract with transcription, candidate selection,
   approval, render, and verification gates.
5. Fan out transcription and candidate analysis as independently keyed units.
6. Record each producer claim and run mechanical and editorial verification.
7. Surface candidates to the human director; persist the chosen directive.
8. Invalidate only units affected by that directive and render the selected set.
9. Complete only when every required deliverable has accepted evidence.
10. If a missing deterministic capability was created during the run, keep it
    local until its promotion policy is satisfied.
```

The same model applies to incident response, research, data operations,
compliance review, customer support, or software delivery. The Domain Pack
changes; the contract plane does not.

## Project status

ContractPlane is in its design and reference-implementation phase. RFD 0001 is
**Proposed**, the DomainPack `v1alpha1` schema is an alpha candidate, and the
local state kernel is experimental. Documents marked as RFD remain proposals
until accepted through [GOVERNANCE.md](GOVERNANCE.md). Do not infer wire
compatibility, security enforcement, or production readiness from an example,
candidate schema, or experimental profile.

Machine-readable project identifiers and schemas use the `contractplane.dev`
namespace. A website URL, package name, or shared acronym alone is not a
conformance claim; accepted schemas and conformance results remain authoritative.

The next milestones are tracked in [STATUS.md](STATUS.md). In particular, the
project still needs accepted core semantics, executable runtime adapters,
effective authority enforcement, independent Verdicts, scoped invalidation, and
capability promotion conformance before it can claim the full architecture.

The broader roadmap is:

1. accept the core object and event model;
2. promote the DomainPack candidate through the governance process;
3. add conforming runtime adapters and authority enforcement;
4. implement independent Verdict, steering, and invalidation semantics;
5. implement governed capability trial, canary, promotion, and rollback;
6. validate the model in at least one non-media domain.

## Contributing

Start with [GOVERNANCE.md](GOVERNANCE.md). Material semantic changes should be
proposed as an RFD. Security-sensitive findings should follow
[SECURITY.md](SECURITY.md), not a public issue.

## License

Code and the machine-readable specification are Apache-2.0. The whitepaper is
CC BY 4.0. Imported Domain Packs retain their source licenses; the OpenClip
fixture is MIT. See [NOTICE](NOTICE) for the exact boundaries.
