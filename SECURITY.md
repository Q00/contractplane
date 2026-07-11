# ContractPlane Security

## 1. Security posture

ContractPlane governs systems that can invoke models, execute tools, access
files and secrets, spend money, and change external state. An Execution Contract
is therefore a security boundary, not just a workflow description.

The default posture is:

- deny authority that is not explicitly granted;
- treat intent, attached content, Domain Packs, model output, worker output, and
  candidate capabilities as untrusted at their respective boundaries;
- separate local reversible work from external or irreversible effects;
- require evidence and an accepted verdict before gated transitions;
- preserve provenance without putting secrets or private reasoning into the
  ledger;
- fail closed when a security-relevant policy or adapter feature is unsupported.

This document describes target security requirements. The repository is in an
early design and reference-implementation phase; do not assume production
hardening until a release explicitly claims and demonstrates it. In `v0.1`,
permissions and side effects are declarative data only. The kernel does not
invoke bindings, authenticate approval actors, enforce effective authority,
verify collector independence, or implement capability sandbox/canary/rollback.
See [STATUS.md](STATUS.md).

## 2. Reporting a vulnerability

Do not report a suspected vulnerability in a public issue, discussion, pull
request, example, or test fixture if doing so would expose users.

Use [GitHub private vulnerability reporting](https://github.com/Q00/contractplane/security/advisories/new)
for this repository. If that form is unavailable, open a minimal public issue
titled `Private security contact requested` without technical details. A
maintainer will establish a private channel before you send secrets, private
user data, or a weaponized proof of concept.

Include, where possible:

- affected version, commit, specification profile, adapter, and Domain Pack;
- threat scenario and impact;
- minimum reproduction without real credentials or private user data;
- whether exploitation requires a trusted pack, local access, network access,
  or user approval;
- proposed mitigation or containment;
- whether public disclosure is already known.

Maintainers should acknowledge a valid private report promptly, coordinate a
remediation and disclosure timeline with the reporter, and issue revocation or
upgrade guidance when a compromised Domain Pack, adapter, or capability may
remain in use.

## 3. Security scope

Security-relevant components include:

- Intent Gateway and input normalization;
- Domain Pack discovery, validation, signature, and activation;
- Environment inspection and policy resolution;
- contract compilation and revision;
- scheduler, ledger, and state reducers;
- runtime and transport adapters;
- capability registry, sandbox, and promotion controller;
- secret resolution;
- evidence collection and verdict issuance;
- human approvals, directives, and overrides;
- artifacts, object storage, logs, traces, metrics, and exports;
- conformance fixtures that assert security behavior.

Model providers, remote tools, package registries, workflow engines, and storage
systems remain separate trust domains even when reached through a trusted
adapter.

## 4. Assets to protect

- user and organization data;
- credentials, tokens, signing keys, and secret references;
- filesystem and process integrity;
- cloud, repository, messaging, deployment, and financial accounts;
- Domain Pack, contract, policy, and capability integrity;
- ledger ordering and audit provenance;
- evidence authenticity and confidentiality;
- approval and actor identity;
- budgets and rate limits;
- availability of schedulers and verification gates;
- the distinction between claimed and confirmed work;
- capability trust tiers and revocation state.

## 5. Adversaries and failure assumptions

The threat model assumes any of the following may be malicious, compromised,
incorrect, or merely overconfident:

- user-supplied or retrieved content containing prompt injection;
- a model or agent role;
- a worker that fabricates completion or evidence;
- a Domain Pack or transitive reference from an untrusted source;
- a candidate or shared capability;
- an adapter that overstates cancellation, sandbox, or permission enforcement;
- a remote service or transport peer;
- an evidence collector or model judge;
- a human account with stolen credentials;
- duplicated, reordered, delayed, or partially committed distributed events.

The design does not assume that model output is trustworthy because it conforms
to a schema. Schema validity establishes shape, not truth or authorization.

## 6. Trust boundaries

### 6.1 Intent versus policy

User intent and attached data enter as untrusted content. The gateway MUST keep
original content separate from system policy and pack instructions. Retrieved
documents, transcripts, webpages, issue bodies, and tool output MUST NOT gain
instruction precedence merely because a model can read them.

### 6.2 Discovery versus activation

Registry discovery MUST use inert metadata. Listing a Domain Pack or capability
MUST NOT execute its code, import its dependencies, resolve its secrets, or run
its installation hooks. Activation requires validation and trust policy.

### 6.3 Contract plane versus execution plane

Runtime adapters receive bounded Unit contracts. They MUST NOT infer additional
authority from ambient environment variables, host filesystem access, inherited
cloud identity, or framework defaults.

### 6.4 Producer versus verifier

The producer's Claim is untrusted evidence about its own work. A required
independent verifier MUST execute in the isolation context declared by policy
and MUST obtain the subject independently where feasible.

### 6.5 Capability author versus promoter

The actor or agent that authors a capability MUST NOT be the sole authority that
promotes it to shared use. Promotion requires policy-defined independent review
and evidence.

### 6.6 Local versus external effects

External mutation—including repository push, deployment, publication, message
send, purchase, data deletion, or remote configuration—requires an explicit
effect classification. Local preparation of a proposal or artifact MUST remain
separate from authorization to publish it.

## 7. Authority model

Every Unit carries an effective Authority Envelope. At minimum, implementations
must be able to distinguish:

- filesystem read roots;
- filesystem write roots;
- process execution and executable allowlists;
- network destinations and protocols;
- secret references;
- monetary or token spend;
- external mutation categories and targets;
- ability to spawn or delegate;
- ability to read or write each memory class;
- ability to collect or issue Evidence and Verdicts.

Authority follows these rules:

1. Unspecified authority is denied.
2. Delegation can narrow but cannot widen authority.
3. An adapter may enforce a stricter policy than the contract.
4. A Directive changes desired work but does not grant authority.
5. An Approval binds to a concrete request, scope, actor, and expiry.
6. Broad reusable grants require explicit policy and must remain visible.
7. Failure to enforce a required restriction is an adapter incompatibility, not
   a warning.

## 8. Secret handling

- Contracts, plans, Unit keys, prompts, claims, evidence, logs, and exports
  SHOULD contain opaque secret references, not secret values.
- Secret values SHOULD be resolved inside the narrowest execution boundary and
  as late as practical.
- Adapters MUST prevent secrets from entering child environments unless the
  Unit explicitly requires them.
- Candidate capabilities SHOULD run with a scrubbed environment and no network
  by default.
- Redaction MUST apply to structured fields and streamed chunks, not only final
  text.
- Hashing a low-entropy secret is not sufficient redaction.
- Secret rotation MUST be possible without changing semantic Unit identity when
  the secret version is not an intended input; where it is an intended input, an
  opaque version identifier may participate in invalidation.

## 9. Prompt injection and confused-deputy defense

ContractPlane does not solve prompt injection by itself. It limits blast radius
through contract boundaries.

- Treat retrieved content and tool output as data with explicit provenance.
- Do not concatenate untrusted text into system policy or adapter configuration.
- Give workers only the tools, memory, paths, and network access required by
  their Unit.
- Require an Approval for sensitive actions even if a document instructs the
  model to perform them.
- Validate tool arguments against schemas and policy after model generation and
  before execution.
- Separate proposal generation from effect execution.
- Record which untrusted sources influenced a Claim when practical.
- Use deterministic parsers and allowlists for control fields rather than asking
  a model to interpret security policy.

## 10. Domain Pack security

A Domain Pack should be treated like executable supply-chain input even if it
contains only declarative files and prompts.

Activation policy SHOULD verify:

- schema and specification version;
- source, digest, and signature where required;
- referenced capability and adapter versions;
- requested permissions and side effects;
- use of raw shell commands or dynamic code;
- remote references and mutable version ranges;
- instruction content that attempts to override host policy;
- evidence and verifier conflicts of interest;
- retention, export, and secret requirements;
- revocation and compatibility status.

Domain Pack policy cannot override immutable host or organization safety policy.
A pack update creates a new immutable version and must not mutate the semantics
of existing run records.

## 11. Capability supply chain

A capability manifest should declare:

- stable identity and immutable version;
- source and build provenance;
- input and output schema;
- permissions, side effects, and output paths;
- network and secret requirements;
- dependencies and lock information;
- self-test and negative tests;
- determinism expectations;
- artifact and evidence contract;
- supported platforms;
- trust tier, review, and revocation.

Promotion controls SHOULD include:

- static source and dependency analysis;
- sandboxed self-test with resource limits and scrubbed secrets;
- output-contract validation and non-zero failure behavior;
- representative inputs, including adversarial and failure cases;
- filesystem and network egress monitoring;
- independent source review;
- signature or attestation;
- canary activation and bounded blast radius;
- reliability thresholds based on more than one author-controlled run;
- rollback and emergency revocation.

A static deny-list is useful but insufficient. Obfuscation, dynamic imports,
dependency compromise, path traversal, symlink attacks, archive extraction, and
resource exhaustion require runtime isolation and explicit tests.

## 12. Sandbox requirements

For untrusted or trial capabilities, the sandbox SHOULD provide:

- a read-only base image or filesystem where possible;
- explicit read and write mounts;
- no inherited credentials;
- disabled network or destination allowlists;
- process, CPU, memory, file-size, file-count, and wall-time limits;
- system-call or container restrictions appropriate to the platform;
- path canonicalization and symlink defense;
- isolated temporary directories;
- captured exit status and structured output;
- cleanup that does not delete user-owned paths;
- a record of the effective sandbox policy.

“Local execution” is not synonymous with “safe execution.”

## 13. Evidence and verifier security

Evidence can be forged, stale, misbound, or selectively omitted.

- Evidence MUST bind to the exact subject, Unit revision, and attempt.
- Freshness and environment constraints MUST be checked.
- Integrity metadata SHOULD be content-addressed or signed when the threat model
  includes storage tampering.
- A verifier SHOULD acquire the artifact independently rather than accept only a
  producer-provided summary.
- Deterministic evidence SHOULD precede model-assisted review.
- Model-assisted Evidence MUST record the rubric, model/provider identity,
  relevant configuration, and inputs or protected references.
- Independence policy SHOULD account for shared model and prompt bias, not only
  different process identity.
- Human overrides MUST preserve failed or missing evidence and stated risk.
- An evidence collection error MUST never become a pass.

## 14. Ledger and event security

- Events MUST be append-only from the portable model's perspective.
- Event writers MUST be authenticated and authorized for the event types they
  emit.
- Reducers MUST be idempotent under duplicate delivery.
- Ordering guarantees and partition keys MUST be documented.
- Corrections append superseding events; they do not rewrite history.
- Integrity protection SHOULD use hashes, signatures, write-once storage, or an
  external audit sink according to risk.
- Sensitive payloads SHOULD live in protected object storage with redacted
  references in the ledger.
- Export MUST support data minimization and field-level redaction.
- Audit retention and privacy deletion obligations must be reconciled
  explicitly; retaining a digest may still be personal data in some contexts.

## 15. Distributed execution hazards

Implementations MUST represent uncertainty honestly.

- Use leases and fencing tokens to prevent stale workers from committing current
  state.
- Treat duplicate delivery as expected and keep effect idempotency explicit.
- If a crash occurs after an external effect but before acknowledgment, mark the
  effect as unknown and reconcile before retrying.
- Cancellation request, worker acknowledgment, and confirmed effect cessation
  are different events.
- Do not rely on wall-clock order across machines without a defined ordering
  mechanism.
- Approval expiry and revocation must be checked at effect time, not only queue
  time.
- Network partition must not convert a policy check into implicit approval.

## 16. Budget and denial-of-service controls

Contracts SHOULD bound:

- model tokens and monetary cost;
- tool and model call counts;
- concurrent Units and delegated depth;
- retry and verification loops;
- wall time, CPU, memory, storage, and output size;
- network requests and downloaded bytes;
- evidence and trace retention;
- human approval queue lifetime.

Budget metrics may lag. Hard enforcement should occur at the nearest reliable
boundary and include a safety margin where usage is asynchronous.

## 17. Data privacy

- Classify input, artifact, memory, evidence, trace, and export data.
- Minimize the data passed to each worker and verifier.
- Make memory scope explicit; subagents should not inherit full parent history by
  default.
- Define retention and deletion per class.
- Avoid storing private model chain-of-thought. Store decisions, structured
  rationale, citations, and observable evidence instead.
- Make cross-border and third-party provider transmission visible in the
  contract environment.
- Do not use user data to promote or benchmark capabilities outside the agreed
  scope without authorization.

## 18. Human identity and approval security

- Authenticate approving actors according to effect risk.
- Display the exact action, target, authority, and material arguments before
  approval.
- Protect against approval replay by binding request ID, nonce or version,
  expiry, and contract revision.
- Require reapproval when material arguments or target change.
- Keep denial and timeout distinct.
- High-risk override policy SHOULD require stronger authentication or multiple
  reviewers.
- Steering channels MUST NOT accept secrets as ordinary directive text.

## 19. Adapter security contract

An adapter MUST declare rather than imply:

- authentication and transport protection;
- sandbox and permission enforcement;
- secret injection behavior;
- cancellation and suspension guarantees;
- durability and duplicate delivery;
- remote file or artifact behavior;
- log and trace redaction;
- supported approval semantics;
- known framework defaults that conflict with ContractPlane policy.

For example, a Mastra Agent Client Protocol adapter must not rely on Mastra's
documented default of selecting the first permission option. It must map
permission requests to the ContractPlane Authority Envelope or suspend for an
explicit decision.

## 20. Security conformance

Security fixtures should test at least:

- unknown permission fields fail closed;
- child authority cannot exceed parent authority;
- secrets are absent from portable exports;
- untrusted tool output cannot create an Approval;
- stale Evidence cannot confirm a new Unit revision;
- producer identity fails an independent verifier requirement;
- duplicate events do not double-approve or double-transition;
- external effect uncertainty blocks unsafe retry;
- revoked capability versions cannot be selected for new contracts;
- a Directive cannot grant network or external mutation authority;
- unsupported adapter security semantics fail compilation;
- proposal packet generation does not publish externally.

## 21. Secure deployment checklist

Before production use, operators should verify:

- a supported, non-draft specification and conformance profile;
- authenticated ledger writers and protected storage;
- Domain Pack and capability source policy;
- sandbox availability and enforcement tests;
- explicit adapter permission maps;
- secret manager integration and redaction tests;
- approval identity and replay protection;
- budget and retry bounds;
- evidence freshness and verifier independence;
- revocation and incident-response procedures;
- backups and recovery tests;
- private vulnerability reporting and update channels.

## 22. Protocol-name safety

Shared acronyms can produce dangerous configuration mistakes. Documentation,
package metadata, adapters, and network endpoints MUST spell out whether they
refer to:

- ContractPlane / Agent Contract Plane;
- Agent Client Protocol; or
- Agent Communication Protocol / its A2A migration path.

No software should select a parser, transport, or permission policy solely from
the string `ACP`.
