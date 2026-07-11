#!/usr/bin/env cwl-runner
# EXPERIMENTAL composite baseline: PROV-style provenance record for a run that
# cleared every upstream gate.
cwlVersion: v1.2
class: CommandLineTool
label: composite-provenance-log
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: provenance_log.py}
    inputBinding: {position: 0}
  token:
    type: File
    inputBinding: {position: 1}
  claim:
    type: File
    inputBinding: {position: 2}
  dataset:
    type: File
    inputBinding: {position: 3}
outputs:
  provenance:
    type: File
    outputBinding: {glob: provenance.json}
