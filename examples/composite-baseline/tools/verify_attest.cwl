#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: recompute + emit a verdict receipt.
cwlVersion: v1.2
class: CommandLineTool
label: composite-verify-attest
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: verify_attest.py}
    inputBinding: {position: 0}
  artifact:
    type: File
    inputBinding: {position: 1}
  dataset:
    type: File
    inputBinding: {position: 2}
outputs:
  verified:
    type: File
    outputBinding: {glob: verified.json}
  receipt:
    type: File
    outputBinding: {glob: verdict-receipt.json}
