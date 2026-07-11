#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: DRIFT-ON-THE-GUARD (a), guard dropped.
#
#   producer -> schema -> policy -> PROV
#
# To drop the expensive verify step from the safe hardened workflow you must also
# drop the accept-gate that references its receipt (otherwise the workflow fails
# to load -- see report-hardened-omitverify.cwl). An integrator refactoring the
# pipeline naturally deletes BOTH governance steps, arriving here. This LOADS and
# runs fully GREEN; an overclaim is accepted. Nothing in CWL requires a workflow
# to contain an accept-gate at all -- the guard itself has no guard.
cwlVersion: v1.2
class: Workflow
label: composite-report-hardened-noguard
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
  policy:
    run: ../tools/policy_gate.cwl
    in: {token: schema_gate/checked, effect: effect}
    out: [authorized]
  provenance:
    run: ../tools/provenance_log.cwl
    in: {token: policy/authorized, claim: claim, dataset: dataset}
    out: [provenance]
