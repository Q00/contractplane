#!/usr/bin/env cwl-runner
# EXPERIMENTAL hardened composite: producer self-attestation forger.
cwlVersion: v1.2
class: CommandLineTool
label: composite-forge-receipt
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: forge_receipt.py}
    inputBinding: {position: 0}
  artifact:
    type: File
    inputBinding: {position: 1}
outputs:
  receipt:
    type: File
    outputBinding: {glob: verdict-receipt.json}
