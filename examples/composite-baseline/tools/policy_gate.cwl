#!/usr/bin/env cwl-runner
# EXPERIMENTAL composite baseline: policy gate via a real `opa eval`. Exit 1
# (permanentFail) when the effect is denied by the Rego policy.
cwlVersion: v1.2
class: CommandLineTool
label: composite-policy-gate
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: policy_gate.py}
    inputBinding: {position: 0}
  token:
    type: File
    inputBinding: {position: 1}
  effect:
    type: File
    inputBinding: {position: 2}
  policy:
    type: File
    default: {class: File, location: ../policy/authorization.rego}
    inputBinding: {position: 3}
outputs:
  authorized:
    type: File
    outputBinding: {glob: authorized.json}
