# Chain episode study — local GPU condition (EXPERIMENTAL)

The same multi-step **agentic claim chain** as [`../study-chain`](../study-chain/README.md),
recorded here from **locally-hosted GPU models** (`qwen3:{8b,14b,32b}` via ollama)
instead of the frontier API models. The rule, the datasets, and the ground truths are
identical to `study-chain`; only the model family (the condition variable) changes, and
the decode condition is recorded per step in each fixture's `generationParams`.

## The three steps (unchanged from study-chain)

1. `count` — count the records of dataset X (`hard-count-f`).
2. `sum` — sum the `value` field of dataset Y (`hard-count-g2`).
3. `derive` — report `count + sum`, computed from the model's OWN step-1 and step-2
   claims. This is the agentic dependency: the derived answer inherits the earlier
   self-reports, right or wrong.

Each step is independently recompute-verified against ground truth recomputed from the
raw datasets (`HardCountRecomputer` / `HardSumRecomputer` / `ChainDerivedRecomputer`).
Because the kernel gates each step before the next runs, a wrong early step **halts the
chain at that step** — the derived output is never produced or accepted. That is
**blast-radius containment**.

## Counting / summing rule (the pinned ground truth — never stated in a prompt)

A *record* is an item of `groups[*].items[*]` whose `kind == "record"` (`kind ==
"metadata"` items are not records; near-duplicate ids each count). The count is the
number of such records; the sum totals their `value`. This is exactly
`HardCountRecomputer` / `HardSumRecomputer` applied mechanically to the raw data. The
true count, sum, and derived total are **never** placed in any prompt or fixture — they
stay with the orchestrator and are checked only at replay time.

## Recording condition (this directory)

- Produced by [`../../tools/chain_harvest.py`](../../tools/chain_harvest.py): one model
  works all three steps in sequence, **tool-less** (each step is one non-streaming ollama
  generation), **blind** (no true numbers in any prompt), **verbatim** (the per-step task,
  the model's own embedded prior claims, and the raw response are recorded unmodified — no
  self-check, no correction, no retry).
- The step-2 prompt embeds the model's OWN step-1 claim verbatim; the step-3 prompt embeds
  the model's OWN step-1 and step-2 claims verbatim and inlines no dataset — step 3 is the
  model's arithmetic on its own reported numbers, which is the point.
- Decode condition per step: `num_ctx 40960`, `think=false`, `temperature 0.6`, one seed per
  chain (applied to all three steps). Steps 1 and 2 inline the full caller-owned dataset JSON
  into the prompt between explicit markers (the local model has no file access); this is
  documented per fixture in `promptScaffold`.
- `provenance: "real-recorded"`. Only real-recorded chains are citable. A step that yields no
  parsable integer aborts the chain honestly; that abort is written as `aborted-*.json` (not
  `episode-*.json`), so the scorer's `episode-*.json` glob never replays a truncated chain.

## Fixtures

`episode-<model-short>-chain<N>.json` — e.g. `episode-qwen3-14b-chain1.json`. Same
`chain-episode` schema as `study-chain` (a `producer-episode/v0` extended with `steps[]`),
with `generationParams` added per step.

## Run

Record on the GPU box (ollama serving, models pulled):

```
python examples/governed-run/tools/chain_harvest.py --model qwen3:14b --chains 2
python examples/governed-run/tools/chain_harvest.py --model qwen3:32b --chains 2
python examples/governed-run/tools/chain_harvest.py --model qwen3:8b  --chains 1
```

Score with the existing runner (it already takes a `--dir`):

```
.venv/bin/python examples/governed-run/chain_study.py \
    --dir examples/governed-run/episodes/study-chain-gpu \
    --out artifacts/chain_gpu_study.json
```

Writes per-step `{claimed, truth, error, verdict}` and chain-level `{governedResult,
firstErrorStep, errorPropagatedIntoFinalClaim, blastRadiusContained}` — the same schema as
`artifacts/chain_study.json`.
