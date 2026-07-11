#!/usr/bin/env cwl-runner
# EXPERIMENTAL composite baseline: producer step (replays a recorded claim).
cwlVersion: v1.2
class: CommandLineTool
label: composite-producer
baseCommand: [python3]
inputs:
  script:
    type: File
    default: {class: File, location: run_producer.py}
    inputBinding: {position: 0}
  claim:
    type: File
    inputBinding: {position: 1}
outputs:
  artifact:
    type: File
    outputBinding: {glob: artifact.json}
