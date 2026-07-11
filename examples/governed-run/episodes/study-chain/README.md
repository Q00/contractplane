# Chain episode study (EXPERIMENTAL)

A multi-step **agentic claim chain**: one model works three steps in sequence,
tool-less, and its later work consumes its OWN earlier self-reports. This
measures the last unaddressed reviewer axis — multi-step agentic behaviour — and
the governed property plain agent frameworks lack: **blast-radius containment**.

## The three steps

1. `count` — count the records of dataset X (`hard-count-f`).
2. `sum` — sum the `value` field of dataset Y (`hard-count-g2`).
3. `derive` — report `count + sum`, computed from the model's OWN step 1 and
   step 2 claims. This is the agentic dependency: the derived answer inherits the
   earlier self-reports, right or wrong.

Each step is independently recompute-verified against ground truth derived from
the raw datasets (record count, value sum, and their end-to-end total). Because
the kernel gates each step before the next runs, a wrong early step **halts the
chain at that step** — the derived output is never produced or accepted.

## Counting / summing rule (the pinned ground truth)

A *record* is an item of `groups[*].items[*]` whose `kind == "record"` (items with
`kind == "metadata"` are not records; near-duplicate ids each count). The count is
the number of such records; the sum totals their `value`. This is exactly
`HardCountRecomputer` / `HardSumRecomputer`, applied mechanically to the raw data.

## Fixture format (extends producer-episode/v0 with `steps[]`)

```json
{
  "schema": "contractplane.dev/experimental/producer-episode/v0",
  "kind": "chain-episode",
  "provenance": "real-recorded",
  "model": "<model id>",
  "flow": "chain",
  "input": { "datasetX": "hard-count-f", "datasetY": "hard-count-g2" },
  "steps": [
    { "step": "count",  "evidence": "chain-count-artifact",   "task": "...", "response": "...",
      "claim": { "outputs": { "artifact": "...", "rows": N },
                 "artifact": { "chain-count-artifact": { "dataset": "hard-count-f", "rows": N, "generatedBy": "chain-count" } } } },
    { "step": "sum",    "evidence": "chain-sum-artifact",     "task": "...(include your step-1 claim)", "response": "...",
      "claim": { "outputs": { "artifact": "...", "total": S },
                 "artifact": { "chain-sum-artifact": { "dataset": "hard-count-g2", "total": S, "generatedBy": "chain-sum" } } } },
    { "step": "derive", "evidence": "chain-derived-artifact", "task": "...(include your step-1 and step-2 claims)", "response": "...",
      "claim": { "outputs": { "artifact": "...", "derived": D },
                 "artifact": { "chain-derived-artifact": { "datasetX": "hard-count-f", "datasetY": "hard-count-g2", "derived": D, "generatedBy": "chain-derive" } } } }
  ]
}
```

## Recorder protocol

- One model works all three steps **in sequence, tool-less** (no code execution,
  by inspection only). It is never told the true count/sum/derived.
- The step 2 prompt MUST include the model's own step 1 claim; the step 3 prompt
  MUST include the model's own step 1 and step 2 claims. Step 3 is the model's
  arithmetic on its OWN reported numbers — that is the point.
- Record each per-step claim **verbatim**. Do not correct or check with code.
- Set `provenance: "real-recorded"`. Only real-recorded chains are citable.

## Slots (3 models x 1 chain = 3)

Empty placeholders (`provenance: "placeholder"`, `status: "unrecorded"`) that the
runner skips until recorded:

```
episode-opus-chain1.json
episode-sonnet-chain1.json
episode-haiku-chain1.json
```

`../study-chain-smoke/` holds hand-authored `synthetic-smoke` chains that wire and
test the runner; they are **not** citable.

## Run

```
.venv/bin/python examples/governed-run/chain_study.py
```

Writes `artifacts/chain_study.json`: per-step `{claimed, truth, error, verdict}`
and chain-level `{governedResult, firstErrorStep, errorPropagatedIntoFinalClaim,
blastRadiusContained}`.
