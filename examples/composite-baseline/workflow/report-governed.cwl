#!/usr/bin/env cwl-runner
# EXPERIMENTAL composite baseline: the CORRECTLY-configured governed pipeline.
#
# Replicates the examples/governed-run report flow out of independent parts:
#   producer -> schema-gate -> independent-verify -> policy-gate -> provenance.
# Any gate that fails exits non-zero, which cwltool turns into a permanentFail:
# a RED pipeline == a rejected run. A fully green run == an accepted run.
cwlVersion: v1.2
class: Workflow
label: composite-report-governed
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
    run: ../tools/verify_recompute.cwl
    in: {artifact: schema_gate/checked, dataset: dataset}
    out: [verified]
  policy:
    run: ../tools/policy_gate.cwl
    in: {token: verify/verified, effect: effect}
    out: [authorized]
  provenance:
    run: ../tools/provenance_log.cwl
    in: {token: policy/authorized, claim: claim, dataset: dataset}
    out: [provenance]
