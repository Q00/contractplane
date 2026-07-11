#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: meta accept-gate. Exit 1 (permanentFail) when
# no valid pass receipt bound to the artifact is present.
cwlVersion: v1.2
class: CommandLineTool
label: composite-accept-gate
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: accept_gate.py}
    inputBinding: {position: 0}
  artifact:
    type: File
    inputBinding: {position: 1}
  receipt:
    type: File
    inputBinding: {position: 2}
  policy:
    type: File
    default: {class: File, location: ../policy/meta_accept.rego}
    inputBinding: {position: 3}
outputs:
  accepted:
    type: File
    outputBinding: {glob: accepted.json}
