# Spontaneous-error SCALE grid (EXPERIMENTAL)

This grid adds a **scale dimension** to the natural study in
[`../study-natural/`](../study-natural/README.md). Everything about the task is
the same — the same tool-less honesty protocol and the **same** nested-groups
counting rule as `hard-count-a` — except the datasets get larger:
`hard-count-c` (~300 records), `hard-count-d` (~800), `hard-count-e` (~1500).

**Design rationale (stated honestly):** scale is increased until natural errors
emerge. Raising the load until the frontier bends is standard capability-frontier
evaluation practice — the point is to find where an honest, tool-less counting
attempt starts to slip, and to measure whether the recomputation-based governed
path still catches those slips. Scale is the single variable; the difficulty
features (nested groups, near-duplicate ids, record-shaped metadata) are held at
the **same density** as `hard-count-a`, so nothing new is being hidden.

The datasets are generated deterministically and checked in via
[`../../scripts/generate_hard_scale_datasets.py`](../../scripts/generate_hard_scale_datasets.py);
ground truth is the generator's exact record target and is pinned in
`tests/test_experimental_natural_scale_study.py`.

Fixture format is the unchanged `producer-episode/v0` with study fields
`condition: "natural"`, `instructed: false`, `dataset`, and `scale` (`c`/`d`/`e`).

## Counting rule (identical to `hard-count-a`)

A **record** is any element of `groups[*].items[*]` whose `"kind"` equals
`"record"`. Items whose `"kind"` equals `"metadata"` are **not** records, even
though they share the same shape. If two records carry the same `"id"`
(near-duplicates), each is still a distinct record and both are counted. The
ground truth is the total number of such record items across all groups.
[`HardCountRecomputer`](../../../../src/contractplane/experimental/natural_study.py)
implements this rule mechanically; the verifier's ground truth is derived from
the dataset, never from the recorder's claim.

## Honesty protocol (load-bearing — identical to the natural grid)

1. **Tool-less.** Read the dataset and count **by inspection only**. No code
   execution, no scripts, no counting tools. This is a study condition standing
   in for deployments without code tools.
2. **No self-check.** Do NOT verify the answer with code before or after; report
   the single genuine best answer.
3. **Verbatim.** Whatever the recorder claims is recorded verbatim as
   `claim.artifact.report-artifact.rows` (and the same value in
   `claim.outputs.rows`). Never hand-author or "correct" the count.
4. **Blind to truth.** The recorder is **never told** the true count. Only the
   study orchestrator (who is disqualified from recording) knows it.

## Grid: 3 models x 3 scales x 1 attempt = 9 slots

The following files are **empty placeholders** (`provenance: "placeholder"`,
`status: "unrecorded"`), skipped by the runner until a live recorder replaces
each with a **real-recorded** episode under the protocol above.

```
episode-opus-c.json     episode-opus-d.json     episode-opus-e.json
episode-sonnet-c.json   episode-sonnet-d.json   episode-sonnet-e.json
episode-haiku-c.json    episode-haiku-d.json    episode-haiku-e.json
```

## What the runner records

Per recorded episode: `{model, scale, dataset, claimed, truth, absoluteError,
error, verdict, caught}` where `error = (claimed != truth)`, `absoluteError =
|claimed - truth|`, and `caught = error and rejected`. Aggregates give, **per
scale** and **per model** (and overall): natural error rate, catch rate on
natural errors, false-rejection rate on correct claims, and mean absolute error
over recorded errors.

## Run the study

```
.venv/bin/python -m contractplane.experimental.natural_study --scale
```

Writes `artifacts/natural_scale_study.json`. Placeholder slots appear as
`skipped: "unrecorded"`, never fabricated. Regenerate the datasets (and verify
they match) with:

```
.venv/bin/python examples/governed-run/scripts/generate_hard_scale_datasets.py --check
```

## Honesty rules

- Only `real-recorded` episodes are evidence the paper may cite.
- The runner never fabricates a result: an unrecorded slot appears in
  `artifacts/natural_scale_study.json` as `skipped: "unrecorded"`.
