#!/usr/bin/env cwl-runner
# EXPERIMENTAL composite baseline: independent verification (recompute row count
# from the caller-owned dataset). Exit 1 (permanentFail) on any mismatch.
cwlVersion: v1.2
class: CommandLineTool
label: composite-verify-recompute
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: verify_recompute.py}
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
