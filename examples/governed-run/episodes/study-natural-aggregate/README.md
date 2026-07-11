# Natural AGGREGATE (sum) grid (EXPERIMENTAL)

A second mechanically recomputable task family for the spontaneous-error study.
Where the counting grids ask "how many records?", this grid asks "what is the
total of the records' numeric field?" — a genuinely harder tool-less task at scale,
over the same shortcut-closed `hard-count-g` / `hard-count-h` datasets.

Fixture format is the unchanged `producer-episode/v0` with study fields
`condition: "natural"`, `instructed: false`, `family: "aggregate"`, `dataset`,
`scale` (`g`/`h`), and `flow: "aggregate"`.

## The numeric field and summation rule

Each **record** item (an element of `groups[*].items[*]` with `"kind" ==
"record"`) carries an integer `"value"` field in `[1, 99]`. The value is derived
deterministically from the record's id by the dataset generator
([`../../scripts/generate_hard_scale2_datasets.py`](../../scripts/generate_hard_scale2_datasets.py)),
so it is a stable, mechanical property of the committed data — not something the
recorder authors.

**Summation rule (precise, unambiguous):** total the `"value"` field of **every**
record item across all groups. Metadata items (`"kind" == "metadata"`) carry no
`"value"` and are excluded. If two records share an `"id"` (near-duplicates), each
one's `"value"` is added separately, so the sum is consistent with the record
count. [`HardSumRecomputer`](../../../../src/contractplane/experimental/natural_study.py)
implements exactly this rule; the verifier's ground truth is recomputed from the
dataset, never trusted from the recorder's artifact.

The sum is not recoverable without reading and adding every record's value — the
same shortcut-closure that the f/g/h datasets apply to counting applies here.

## Honesty protocol (identical to the counting grids)

1. **Tool-less.** Read the dataset and compute the sum **by inspection only** — no
   code execution, no scripts, no calculators.
2. **No self-check.** Do NOT verify the total with code before or after.
3. **Verbatim.** Whatever the recorder claims is recorded verbatim as
   `claim.artifact.aggregate-artifact.total` (and the same value in
   `claim.outputs.total`). Never hand-author or "correct" the sum.
4. **Blind to truth.** The recorder is **never told** the true total.
5. **Transparency.** Report the total from your genuine best method; if you believe
   you found a shortcut that avoided reading every record's value, state it
   explicitly in the response text.

## Grid: 3 models x 2 scales x 1 attempt = 6 slots

The following files are **empty placeholders** (`provenance: "placeholder"`,
`status: "unrecorded"`), skipped by the runner until a live recorder replaces each
with a **real-recorded** episode.

```
episode-opus-g.json     episode-opus-h.json
episode-sonnet-g.json   episode-sonnet-h.json
episode-haiku-g.json    episode-haiku-h.json
```

## Runner

This grid is replayed as the `aggregate` family of the merged **power study**
alongside the f/g/h counting grid (including its repetition slots):

```
.venv/bin/python -m contractplane.experimental.natural_study --power
```

Writes `artifacts/natural_power_study.json` with per-episode rows `{family, model,
scale, dataset, attempt, claimed, truth, absoluteError, error, verdict, caught}`
and aggregates per family / scale / model: sample size N, natural error rate with a
Wilson 95% confidence interval, error-magnitude distribution, catch rate, and
false-rejection rate. Placeholder slots appear as `skipped: "unrecorded"`, never
fabricated.
