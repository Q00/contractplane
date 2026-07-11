#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: the reviewer's proposed fix, wired SAFELY.
#
#   producer -> schema -> verify-attest -> accept-gate(meta-policy) -> policy -> PROV
#
# The accept-gate enforces "an accept requires a preceding verify verdict receipt".
# Critically, its `receipt` input is sourced from the verify step's output
# (verify/receipt) -- a type-coupled dependency. A correct claim clears verify,
# gets a real pass receipt, and the accept-gate allows. This is the configuration
# in which the composite genuinely enforces the invariant.
cwlVersion: v1.2
class: Workflow
label: composite-report-hardened
inputs:
  claim: File
  schema: File
  dataset: File
  effect: File
outputs:
  provenance:
    type: File
    outputSource: provenance/provenance
steps:
  producer:
    run: ../tools/run_producer.cwl
    in: {claim: claim}
    out: [artifact]
  schema_gate:
    run: ../tools/schema_validate.cwl
    in: {artifact: producer/artifact, schema: schema}
    out: [checked]
  verify:
    run: ../tools/verify_attest.cwl
    in: {artifact: schema_gate/checked, dataset: dataset}
    out: [verified, receipt]
  accept_gate:
    run: ../tools/accept_gate.cwl
    in: {artifact: schema_gate/checked, receipt: verify/receipt}
    out: [accepted]
  policy:
    run: ../tools/policy_gate.cwl
    in: {token: accept_gate/accepted, effect: effect}
    out: [authorized]
  provenance:
    run: ../tools/provenance_log.cwl
    in: {token: policy/authorized, claim: claim, dataset: dataset}
    out: [provenance]
