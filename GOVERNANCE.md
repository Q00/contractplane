# ContractPlane Governance

## 1. Purpose

This document defines how ContractPlane specifications, reference
implementations, adapters, Domain Packs, and conformance claims evolve.

The project values:

- portable semantics over framework-specific convenience;
- evidence over assertion;
- recorded rationale over invisible convention;
- security and user authority over autonomous expansion;
- small interoperable cores over one universal framework;
- reversible experiments and explicit promotion;
- factual comparison with neighboring projects.

The product is **ContractPlane** and the formal architecture is the **Agent
Contract Plane**.

The canonical project and specification namespace is
[`contractplane.dev`](https://contractplane.dev/). Control of that namespace is
an operational project asset; changes to normative semantics still follow this
governance process.

## 2. Naming and ecosystem relationships

ContractPlane is independent of and not affiliated with:

- Agent Client Protocol, which standardizes editor/IDE and coding-agent
  communication; and
- the IBM/BeeAI-origin Agent Communication Protocol, whose documentation states
  that it is now part of A2A under the Linux Foundation.

The project may maintain adapters for those protocols. Governance decisions
must not imply ownership, endorsement, wire compatibility, or replacement of a
neighboring standard.

Public material should prefer `ContractPlane` or `Agent Contract Plane` over the
bare acronym `ACP`.

## 3. Project surfaces

Governance distinguishes these surfaces:

1. **Normative specification**: schemas explicitly accepted through governance
   and semantic requirements in accepted RFDs. The current
   `contractplane.dev/v1alpha1` DomainPack schema is an alpha candidate, and RFD
   0001 remains Proposed; neither is a stable core specification yet.
2. **Reference implementation**: code in `src/` that demonstrates one
   implementation of a stated profile.
3. **Conformance suite**: implementation-neutral fixtures and expected behavior
   in `conformance/`.
4. **Domain Packs**: versioned domain operating contracts in `domain-packs/`.
5. **Adapters**: runtime and transport integrations in `adapters/`.
6. **Examples**: non-normative demonstrations in `examples/`.
7. **Design documentation**: motivation and forward-looking architecture in
   `docs/`, `WHITEPAPER.md`, and draft RFDs.

An example or reference implementation behavior is not normative unless the
specification says so.

Current publication and implementation status is recorded in
[STATUS.md](STATUS.md). Release material must distinguish candidate schemas,
experimental profiles, accepted specifications, and target architecture.

## 4. Roles

### 4.1 Contributor

Anyone who reports issues, proposes designs, improves documentation, writes
tests, or submits code. Contributors are expected to disclose relevant
conflicts, respect security reporting rules, and avoid overstating conformance.

### 4.2 Maintainer

Maintainers review and merge changes, manage releases, triage issues, and uphold
project scope. Maintainer status is based on sustained contribution, sound
judgment, respectful collaboration, and demonstrated care for compatibility and
security.

### 4.3 Specification steward

A maintainer responsible for consistency of the normative core, versioning,
RFD status, and conformance traceability. A steward may block a merge that
creates undocumented semantic drift.

### 4.4 Domain Pack maintainer

An owner of one Domain Pack's semantics, evidence rules, release history, and
compatibility. This role does not grant authority over the core specification.

### 4.5 Adapter maintainer

An owner of one adapter's version matrix, security mapping, conformance results,
and upstream compatibility.

### 4.6 Security responder

A trusted maintainer who can receive private reports, coordinate embargoed
fixes, revoke compromised artifacts, and publish advisories.

### 4.7 RFD editor

A maintainer who checks that an RFD is complete, assigns its status, records the
decision and rationale, and links follow-up implementation work. The editor need
not agree with the proposal.

One person may hold multiple roles. The repository's current maintainer and
ownership configuration is authoritative for who holds them.

## 5. Decision principles

Decisions should optimize, in order:

1. safety and explicit human authority;
2. semantic correctness and auditability;
3. cross-runtime portability;
4. backwards compatibility and migration clarity;
5. implementation simplicity;
6. performance and convenience.

This ordering is a guide, not an excuse to ignore performance or usability.
Tradeoffs must be recorded when higher-priority goals impose material cost.

## 6. Types of change

### 6.1 Editorial change

Typographical fixes, clearer examples, link updates, and wording that does not
change semantics may use an ordinary pull request.

### 6.2 Implementation change

Reference code, tests, or tooling that stays within accepted semantics may use
an ordinary pull request with appropriate tests.

### 6.3 Normative change

A change requires an RFD when it:

- adds, removes, or changes a portable object, field, event, state, transition,
  invariant, or conformance requirement;
- changes authority, evidence, approval, security, or privacy semantics;
- changes compatibility or versioning policy;
- introduces a new extension class or conformance profile;
- changes the governance process itself;
- creates a project-wide dependency or hosted service commitment.

### 6.4 Domain Pack change

A Domain Pack may evolve through its own versioned change process when the
change does not alter core semantics. New authority, external side effects,
evidence weakening, or incompatible behavior requires explicit review and a
version change.

### 6.5 Security emergency

Maintainers may privately prepare and merge a narrowly scoped security fix,
revocation, or release without the normal public review window. The public
record should be completed after coordinated disclosure, without exposing users
prematurely.

## 7. RFD process

RFD means **Request for Discussion**.

### 7.1 Lifecycle

- `Draft`: incomplete or actively authored.
- `Proposed`: ready for public review.
- `Accepted`: approved direction; implementation may still be incomplete.
- `Rejected`: considered and declined with rationale.
- `Withdrawn`: removed by its author.
- `Superseded`: replaced by a later RFD.
- `Final`: accepted, implemented, documented, and covered by conformance where
  applicable.

### 7.2 Required sections

A normative RFD should include:

- summary and motivation;
- scope and non-goals;
- terminology;
- proposed semantics;
- security and privacy impact;
- compatibility and migration;
- conformance plan;
- alternatives considered;
- operational consequences;
- unresolved questions;
- implementation and rollout plan.

### 7.3 Review

The RFD editor verifies completeness and opens the proposal for review. Review
should include affected specification, implementation, Domain Pack, adapter,
security, and operator perspectives. Material objections should be answered in
the RFD or decision record rather than only in a transient conversation.

### 7.4 Decision

The project seeks rough consensus: objections are resolved through evidence,
tests, narrowed scope, or explicit tradeoff. Consensus does not require
unanimity.

If consensus cannot be reached, active maintainers decide. With two or more
eligible maintainers, acceptance requires a simple majority and at least two
affirmative votes for a breaking normative change. During bootstrap governance
with one active maintainer, that maintainer may accept a proposal but must record
the rationale, dissent, and migration impact. Security response may use the
emergency process.

### 7.5 Finalization

An Accepted RFD becomes Final only when:

- normative text and schemas are merged;
- reference implementation behavior is identified or intentionally deferred;
- required migrations are documented;
- conformance fixtures exist for portable behavior;
- security documentation is updated;
- release notes identify compatibility impact.

## 8. Compatibility and versioning

### 8.1 Specification identifiers

Machine-readable artifacts use explicit API and kind identifiers, for example
`contractplane.dev/v1alpha1`. Implementations must report the versions and
profiles they support.

### 8.2 Maturity

- `alpha candidate`: semantics may change; migration is best-effort and the
  artifact is not normative until accepted.
- `beta`: core semantics are stabilizing; breaking changes require migration
  documentation.
- stable major version: breaking changes require a new major version or profile.

### 8.3 Compatibility promises

A project release must distinguish:

- specification compatibility;
- reference implementation version;
- adapter upstream-version support;
- Domain Pack version;
- conformance suite version and profile.

Sharing a field name, object name, or acronym is not compatibility.

### 8.4 Deprecation

Stable features should be deprecated before removal. A deprecation notice should
state replacement, migration, earliest removal version, security impact, and
conformance impact. Compromised behavior may be removed or revoked immediately.

## 9. Conformance governance

- Conformance fixtures are reviewed as normative behavior.
- A fixture must cite the requirement or accepted RFD it tests.
- Vendor- or framework-specific behavior belongs in an adapter profile, not the
  portable core suite.
- Results must state implementation version, suite version, profile,
  environment, skipped tests, and extensions.
- The project may list self-reported and independently verified results
  separately.
- A failing or stale result must not be represented as current full
  conformance.

## 10. Domain Pack governance

A Domain Pack release should include:

- immutable name and version;
- supported ContractPlane version and profile;
- maintainers and source;
- entrypoints, roles, flows, capabilities, evidence, and policy;
- permissions and external side effects;
- compatibility and migration notes;
- tests and representative fixtures;
- security review status;
- revocation channel.

Promotion into an official registry should require successful validation,
security review proportional to authority, representative runs, and a named
maintainer. Official listing does not make every capability safe for every
environment; contract compilation still applies local policy.

## 11. Adapter governance

Adapter maintainers must publish:

- upstream framework or protocol versions tested;
- mapped and unsupported ContractPlane semantics;
- permission and secret behavior;
- cancellation, retry, suspension, and durability guarantees;
- telemetry and redaction behavior;
- conformance profile and results;
- known security-sensitive defaults;
- upgrade and end-of-support policy.

An adapter must not paper over missing behavior. Unsupported required semantics
cause contract incompatibility.

## 12. Capability promotion governance

Capability authorship, audit, and promotion should be separable roles. A
promotion decision considers:

- duplication and correct execution layer;
- manifest completeness;
- self-tests and representative runs;
- permissions and side effects;
- source and dependency provenance;
- independent security review;
- reliability thresholds;
- canary and rollback plan;
- user or organization approval for publication.

Generating a proposal packet is not authorization to create a branch, push,
open a pull request, publish a package, or activate the capability globally.

## 13. Security governance

- Private reports follow [SECURITY.md](SECURITY.md).
- The concrete fallback security contact is
  [security@contractplane.dev](mailto:security@contractplane.dev).
- Security responders may embargo details and revoke artifacts.
- Security-relevant specification changes require security review.
- A policy weakening must be explicit; absence of reviewer response is not
  approval.
- Maintainers disclose conflicts with vendors, adapters, or capabilities when
  material to a decision.
- Post-incident reports should record root cause, detection gap, affected
  versions, remediation, and conformance changes without exposing private user
  data.

## 14. Maintainer changes

New maintainers are nominated by an existing maintainer and accepted based on
sustained contribution and project judgment. Inactive maintainers may move to
emeritus status after reasonable private contact. Removal for security risk,
abuse, or persistent governance violation requires a recorded maintainer
decision, with private handling where disclosure would create harm.

The project should avoid concentrating release, registry, and security keys in
one account as it grows.

## 15. Conduct

Participation must be professional, inclusive, and focused on technical
substance. Harassment, personal attacks, doxxing, credential exposure, and
deliberate misrepresentation of security or conformance are unacceptable.

The project should adopt a dedicated Code of Conduct before broad community
operation. Until then, maintainers may moderate contributions that make safe and
productive collaboration impossible.

## 16. Amendments

Material changes to this governance document require an RFD. Editorial fixes
may use an ordinary pull request. Emergency security procedures may be clarified
after an incident, but changes to decision authority require normal review.
