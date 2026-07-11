# Large-N local-model natural-error grid (EXPERIMENTAL)

This grid extends the capability-frontier characterization of the sibling natural grids
*below* the frontier tier. The frontier grids (`study-natural`, `study-natural-scale2`)
record one or two attempts per Anthropic model; at that scale spontaneous errors are rare,
so the headline was largely a false-rejection bound plus an honest null (paper claim
**C10**). Here we record a **locally-hosted small model** (`qwen3:8b` via
[ollama](https://ollama.com)) at **zero API cost**, which lets N grow to ~20 attempts per
dataset. A weaker model on the same shortcut-closed datasets is expected to make genuine,
non-instructed counting errors at a measurable rate — turning C10's null into a *measured*
"error rate scales with model capability" result while the recomputation gate's catch rate
and 0% false-rejection rate are tested at large N.

## Datasets in scope: f and g only (h excluded, honestly)

The harvester renders the **same** documented counting rule as
[`../study-natural-scale2/`](../study-natural-scale2/README.md) on the shortcut-closed
datasets:

- `hard-count-f` (~273 records, ~34 KB) — fits qwen3:8b's native context.
- `hard-count-g` (~754 records, ~95 KB) — fits native context (measured before harvest).

`hard-count-h` (~1551 records, ~195 KB, ~55 K tokens) is **excluded**: it does not fit
qwen3:8b's ~32–40 K native context, and forcing it in via YaRN RoPE scaling would change
the eval condition. Excluding it is the honest choice; the decision is recorded in
`artifacts/experiments.jsonl`. See `plans/qwen-harvest-plan.md`.

## The dataset is inlined into the prompt

The local model has no file access, so the harvester inlines the full dataset JSON into the
prompt between explicit markers. The **task instructions** (the counting rule + honesty
protocol) are recorded verbatim in each episode's `task`, and `promptScaffold` records that
the dataset was delivered inline. Counting is still tool-less by inspection — no code
execution — so the condition matches the frontier grids.

## Honesty protocol (load-bearing, identical to the frontier natural grids)

1. **Tool-less** — count by inspection only; no code, no counting tools.
2. **No self-check** — do not verify the answer with code before or after.
3. **Verbatim** — whatever the model claims is recorded verbatim as
   `claim.artifact.report-artifact.rows`; counts are never hand-authored or corrected.
4. **Blind to truth** — the true count is never placed in the prompt.
5. **No retry-until-parse** — if a response yields no parsable count, the attempt is
   recorded as a `parseFailure` episode (real data on small-model behaviour), counted as
   its own category, never re-prompted, and never scored as a caught error.
6. **Independent attempts** — each attempt varies the ollama sampling seed and cycles
   temperature (0.6 / 0.7 / 0.8), recorded per episode in `generationParams`.

## Decode condition: no-think (recorded), and why

Each episode is recorded with qwen3 **thinking disabled** (`generationParams.think =
false`), so the model reports a direct tool-less estimate rather than an extended
chain-of-thought enumeration. This is recorded verbatim on every episode and is a
deliberate, honest condition, not a hidden choice:

- A think-enabled probe was attempted for a matched arm but proved **impractical**:
  qwen3:8b generated a runaway enumeration CoT exceeding 7,800 tokens at ~16 tok/s
  **without terminating** on a single ~300-record dataset (>9 min, no answer), so a
  large-N think arm is not tractable (recorded as `e16-local-think-mode-probe` in
  `artifacts/experiments.jsonl`). That inability to enumerate hundreds of records by
  reasoning is itself a small-model data point.
- The frontier natural grids were recorded under each model's natural behaviour (which
  included visible enumeration). The no-think local arm therefore differs in decode
  condition; it is best read as a tool-less *estimate* condition and, if anything, a
  lower bound on the difficulty. A matched think-enabled local arm is future work; it is
  not required for the monotone error-rate-by-capability result the study reports.

## Files

Fixtures are `episode-qwen3-<f|g>-<NN>.json` (NN = attempt, zero-padded), each a
`producer-episode/v0` transcript with `provenance: "real-recorded"`, `model: "qwen3:8b"`,
`condition: "natural"`, `instructed: false`. They are written **incrementally** by the
harvester, so a long run's partial progress persists and a re-run resumes.

## Harvest and replay

Harvest (requires a running ollama server with `qwen3:8b` pulled):

```
ollama serve &                       # if not already running
ollama pull qwen3:8b
.venv/bin/python examples/governed-run/tools/local_harvest.py --n 20
```

Replay through the governed path and aggregate (deterministic, offline, no ollama):

```
.venv/bin/python examples/governed-run/local_study_runner.py
```

Writes `artifacts/local_model_study.json`: per-episode rows + per-dataset/overall natural
error rate (with Wilson 95% CI), error-magnitude distribution, catch rate, false-rejection
rate, parse-failure count, and a capability-frontier comparison block.

## Honesty rules

- Only `real-recorded` episodes are evidence. The runner never fabricates: unrecorded /
  malformed slots are skipped or faulted, never invented.
- Parse-failures are recorded outcomes, not errors — they are excluded from the error /
  catch / false-rejection math and reported as a separate `parseFailures` tally.
