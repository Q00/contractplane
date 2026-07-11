#!/usr/bin/env cwl-runner
# EXPERIMENTAL composite baseline: schema gate. Exit 1 (permanentFail) on a
# schema violation, so a format-violation reddens the pipeline before verify.
cwlVersion: v1.2
class: CommandLineTool
label: composite-schema-gate
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: schema_validate.py}
    inputBinding: {position: 0}
  artifact:
    type: File
    inputBinding: {position: 1}
  schema:
    type: File
    inputBinding: {position: 2}
outputs:
  checked:
    type: File
    outputBinding: {glob: checked.json}
