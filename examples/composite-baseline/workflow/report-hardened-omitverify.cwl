#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: the NAIVE omission attempted against the safe
# wiring. The verify step has been deleted, but the accept-gate still references
# `verify/receipt`. This workflow is INTENTIONALLY BROKEN: it is meant to show
# that cwltool's own loader REJECTS it (a dangling step reference), so the naive
# verify-omission cannot even be expressed as a runnable hardened pipeline when
# the receipt is type-coupled to the verifier. The driver captures the load error.
cwlVersion: v1.2
class: Workflow
label: composite-report-hardened-omitverify-BROKEN
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
  # verify step deleted -- but the accept-gate below still sources verify/receipt.
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
