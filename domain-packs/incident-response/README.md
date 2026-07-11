# Incident Response Domain Pack

Incident Response is ContractPlane's second real-domain fixture, and the first
that is **not media and not coding**. It packages a security incident lifecycle —
detect, triage, investigate, contain, notify, postmortem — as one portable,
evidence-gated `DomainPack`, and it exists to test the abstraction's cross-domain
generality claim with a domain whose *shape* differs from OpenClip's, not just
its vocabulary.

Unlike `openclip/`, this pack is authored natively in this repository; there is
no upstream project to sync from, so it ships a native `pack.lock.json`
(`contractplane-domain-native-lock-v1`) rather than an upstream `SOURCE.lock.json`.

## What it exercises that OpenClip did not

- **`integration` capability kind.** OpenClip uses only `deterministic` and
  `agent` capabilities. The containment actions here — `isolate-system` and
  `notify-stakeholders` — are `integration` capabilities: bound external system
  calls executed by an adapter, carrying no agent role.
- **`external` side effects.** OpenClip's every capability is `sideEffects: local`
  (or `none`). This pack's integration capabilities declare `sideEffects:
  external`, the schema's third and previously-unused side-effect class.
- **Human approval *before* an external mutation.** Every external-side-effect
  stage is gated by the `command-authorized` policy (`humanApproval: always`) and
  must carry both an `approval-receipt` (external-receipt from the incident
  commander) and a `containment-receipt` (external-receipt confirming the
  third-party system actually applied the change). OpenClip's `external-receipt`
  evidence attests a human selection or a deterministic probe; here it also
  attests a *side-effecting integration call's* confirmation.
- **Scatter/gather over live scope.** Investigation fans out (`each`) over the
  triage-derived affected systems, gathers back into one deterministic
  root-cause `correlate`, then fans out again (`each`) over the compromised
  subset for containment — a different fan-out topology from OpenClip's
  media-chunk pipeline.

## Flows

- **`respond`** — the full lifecycle: `detect → triage → investigate (each) →
  correlate → plan-mitigation → contain (each, command-authorized) → notify
  (command-authorized) → postmortem → review-postmortem`. The checked-in golden
  plan is `conformance/incident-response/respond.plan.json`.
- **`contain`** — an emergency fast-path: `detect → triage → isolate (each,
  command-authorized) → broadcast (command-authorized)`, for scoping and
  quarantining an active intrusion before a full investigation.

## Current conformance level

- Both flow templates validate and compile into deterministic waves.
- `respond` is the checked-in golden execution-plan fixture with a stable
  `planDigest`.
- All 5 bound roles ship as hash-locked portable contracts under `roles/`.
- Capability bindings, permissions, and adapter `config` are declarative and
  inspectable; ContractPlane does not execute any integration or agent role in
  v0.1.
- Fan-out selectors and the `when` expression are preserved, not evaluated.

## Reproduce locally

```bash
contractplane validate domain-packs/incident-response/incident-response.yaml
contractplane compile domain-packs/incident-response/incident-response.yaml \
  --entrypoint respond --out /tmp/incident-respond.plan.json
```
