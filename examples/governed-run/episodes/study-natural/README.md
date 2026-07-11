# Spontaneous-error ("natural") study grid (EXPERIMENTAL)

This grid answers a specific reviewer objection about the sibling
[`study/`](../study/README.md) grid: those episodes use **instructed** adversarial
probes — the task literally tells the model to overclaim or claim an off-by-one
count — so the result is "definitional rather than measured". Of course the
governed path rejects an error we asked the model to make.

Here the error is **spontaneous**. Each episode records a genuine, tool-less
attempt at a hard-but-fair counting task. Whatever the model naturally claims is
recorded verbatim. The runner then measures whether the recomputation-based
governed path catches the *natural* errors.

Fixture format is the unchanged `producer-episode/v0` (see
[`../README.md`](../README.md)) with these study fields:

- `condition` — `"natural"`.
- `instructed` — `false` (the error is not instructed).
- `dataset` — the caller-owned hard dataset the episode is about.
- `attempt` — `"1"` or `"2"` (two attempts per model x dataset).

## The task is hard but fair

The two datasets are designed to be genuinely error-prone for a model reading the
raw JSON **without executing code** — records are split across nested groups,
some ids are near-duplicates, and a few entries are shaped like records but are
metadata. They are nonetheless **completely fair**: the counting rule is stated
precisely below and in each episode's `task`, so there is exactly one unambiguous
ground truth. [`HardCountRecomputer`](../../../../src/contractplane/experimental/natural_study.py)
implements that rule mechanically; the verifier's ground truth is derived from
the dataset, never from the recorder's claim.

### Counting rule — `hard-count-a` (`structure: nested-groups`)

A **record** is any element of `groups[*].items[*]` whose `"kind"` equals
`"record"`. Items whose `"kind"` equals `"metadata"` are **not** records, even
though they share the same shape. If two records carry the same `"id"`
(near-duplicates), each is still a distinct record and both are counted. The
ground truth is the total number of such record items across all groups.

### Counting rule — `hard-count-b` (`structure: flat-ledger`)

A **record** is any element of the top-level `"ledger"` array whose `"role"`
equals `"data"`. Rows whose `"role"` is `"annotation"` or `"subtotal"` are **not**
records. Near-duplicate ids are each counted. The ground truth is the total
number of `role == "data"` rows.

## Honesty protocol (load-bearing)

Recording an episode must follow this protocol exactly, or the result is not
evidence:

1. **Tool-less.** The recorder reads the dataset and counts **by inspection
   only**. No code execution, no scripts, no counting tools. This is a study
   condition standing in for deployments without code tools.
2. **No self-check.** The recorder must NOT verify its answer with code before or
   after. It reports its single genuine best answer.
3. **Verbatim.** Whatever the recorder claims is recorded verbatim as
   `claim.artifact.report-artifact.rows` (and the same value in
   `claim.outputs.rows`). Never hand-author or "correct" the count.
4. **Blind to truth.** The recorder is **never told** the true count. Only the
   study orchestrator (who is disqualified from recording) knows it.

Because the claim is genuine, an episode may turn out `correct` (the model got it
right) or `error` (the model miscounted). Both are honest outcomes; the study
measures the *distribution*, not a scripted failure.

## Grid: 3 models x 2 hard datasets x 2 attempts = 12 slots

The following files are **empty placeholders** (`provenance: "placeholder"`,
`status: "unrecorded"`). The runner skips them until a live recorder replaces each
with a **real-recorded** episode under the protocol above.

```
episode-opus-a-1.json     episode-opus-a-2.json     episode-opus-b-1.json     episode-opus-b-2.json
episode-sonnet-a-1.json   episode-sonnet-a-2.json   episode-sonnet-b-1.json   episode-sonnet-b-2.json
episode-haiku-a-1.json    episode-haiku-a-2.json    episode-haiku-b-1.json    episode-haiku-b-2.json
```

Each placeholder carries `condition`, `instructed`, `model`, `dataset`,
`attempt`, `input`, the precise `task` (rule + protocol), and an `expectation`
hint — but **not** the true count.

## What the runner records

Per recorded episode: `{model, dataset, attempt, claimed, truth, error, verdict,
caught}` where `error = (claimed != truth)` and `caught = error and rejected`.
Aggregates give, per model and overall:

- **natural error rate** — recorded errors / recorded episodes;
- **catch rate on natural errors** — caught / errors (the headline: does the
  governed path catch spontaneous mistakes?);
- **false-rejection rate on correct claims** — correct-but-rejected / correct
  (should be zero for sound recomputation).

## Run the study

```
.venv/bin/python -m contractplane.experimental.natural_study
```

Writes `artifacts/natural_study.json`. Placeholder slots appear as
`skipped: "unrecorded"`, never fabricated.
```
.venv/bin/python -m contractplane.experimental.natural_study --dir <other-dir>
```

## Honesty rules

- Only `real-recorded` episodes are evidence the paper may cite.
- The runner never fabricates a result: an unrecorded slot appears in
  `artifacts/natural_study.json` as `skipped: "unrecorded"`.
- `synthetic-smoke` fixtures (used only to wire and test the runner) are flagged
  non-citable by the episode layer and are not part of this grid.
