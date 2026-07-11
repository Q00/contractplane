#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: the accept-gate is retained but its verdict
# receipt is now a LOOSE workflow input rather than sourced from the verify step
# (the verify step is gone). This is the realistic drift: receipts come from "an
# external attestation store" the integrator plumbs in. The workflow LOADS and
# RUNS. Whether it fails safe depends entirely on what receipt is supplied:
#   - an honest integrator with no verification supplies a no-verdict receipt
#     (receipts/no-verification.receipt.json) -> accept-gate DENY (red). Caught.
#   - a forged pass receipt -> accept-gate ALLOW (green). Fails open.
# Nothing in CWL or OPA constrains which one is wired in.
cwlVersion: v1.2
class: Workflow
label: composite-report-hardened-loose
inputs:
  claim: File
  schema: File
  dataset: File
  effect: File
  receipt: File
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
  accept_gate:
    run: ../tools/accept_gate.cwl
    in: {artifact: schema_gate/checked, receipt: receipt}
    out: [accepted]
  policy:
    run: ../tools/policy_gate.cwl
    in: {token: accept_gate/accepted, effect: effect}
    out: [authorized]
  provenance:
    run: ../tools/provenance_log.cwl
    in: {token: policy/authorized, claim: claim, dataset: dataset}
    out: [provenance]
