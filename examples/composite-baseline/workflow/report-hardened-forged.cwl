#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: DRIFT-ON-THE-GUARD (b), receipt forgery.
#
#   producer -> schema -> forge-receipt -> accept-gate(meta-policy) -> policy -> PROV
#
# The verify step is gone; a producer-side forger emits a self-attested pass
# receipt with the correct artifact hash. The accept-gate (meta-policy) IS
# present and IS consulted -- but it can only check that a pass receipt bound to
# this artifact exists, not that the verifier wrote it. So an overclaim runs
# fully GREEN and is accepted. The guard is present and still fails open, because
# the trust boundary is in the wiring, which nothing enforces.
cwlVersion: v1.2
class: Workflow
label: composite-report-hardened-forged
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
  forge:
    run: ../tools/forge_receipt.cwl
    in: {artifact: schema_gate/checked}
    out: [receipt]
  accept_gate:
    run: ../tools/accept_gate.cwl
    in: {artifact: schema_gate/checked, receipt: forge/receipt}
    out: [accepted]
  policy:
    run: ../tools/policy_gate.cwl
    in: {token: accept_gate/accepted, effect: effect}
    out: [authorized]
  provenance:
    run: ../tools/provenance_log.cwl
    in: {token: policy/authorized, claim: claim, dataset: dataset}
    out: [provenance]
