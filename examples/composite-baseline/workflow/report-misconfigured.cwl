#!/usr/bin/env cwl-runner
# EXPERIMENTAL composite baseline: the MISCONFIGURED governed pipeline.
#
# This is report-governed.cwl with a single realistic drift: the independent
# `verify` step has been silently dropped (a copy-paste/refactor omission), so
# the schema-gate output flows straight into the policy-gate:
#   producer -> schema-gate -> policy-gate -> provenance.
#
# Nothing about this workflow is invalid CWL. It parses, it type-checks, it runs
# fully GREEN. An overclaim (rows 999 vs ground-truth 12) clears schema (it is a
# well-shaped integer >= 1) and, with no recomputation left to contradict it, is
# ACCEPTED and written into the provenance log as a satisfied run. There is no
# structural signal that a governance step is missing — that is the delta this
# baseline exists to make measurable.
cwlVersion: v1.2
class: Workflow
label: composite-report-misconfigured
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
  # <-- the `verify` step that recomputes row count from the dataset is GONE.
  policy:
    run: ../tools/policy_gate.cwl
    in: {token: schema_gate/checked, effect: effect}
    out: [authorized]
  provenance:
    run: ../tools/provenance_log.cwl
    in: {token: policy/authorized, claim: claim, dataset: dataset}
    out: [provenance]
