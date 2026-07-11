# Spontaneous-error SCALE grid, SHORTCUT-CLOSED (EXPERIMENTAL)

This grid is a methodological fix for [`../study-natural-scale/`](../study-natural-scale/README.md)
(the `hard-count-c/d/e` grid). Inspection found that c/d/e admitted O(1)/O(groups)
shortcuts that let a model report the count **without enumerating the records**:

- record ids were **sequential** (`rec-000001 .. rec-001523`), so the last id
  directly reveals the count; and
- group sizes were **uniform** (13 records per group), so the count is recoverable
  as `groups x 13 + remainder`.

Recorded responses confirmed models used these regularities (structural
multiplication), which fully explains the earlier 9/9 perfect result — the task
was not actually measuring tool-less enumeration at scale. This is an
evaluation-design finding; it is recorded in the experiments ledger
(`e8-scale-shortcut-discovery`) and is worth citing in the paper.

`hard-count-f/g/h` keep the **same** counting rule and the **same** scales
(~300 / ~800 / ~1500 records) but close both shortcuts:

- **record ids are random, shuffled, letter-led base-36 tokens** with no
  sequential or count-revealing structure — no id is a plain integer, the last id
  does not encode the count, and the id order is not sorted; and
- **group sizes are drawn irregularly** in `[3, 31]`, so there is no uniform
  multiplier.

The record-shaped metadata (~10%) and near-duplicate id (~5%) density match the
earlier datasets — scale and shortcut-closure are the only changes, not new
trickery. The datasets are generated deterministically and checked in via
[`../../scripts/generate_hard_scale2_datasets.py`](../../scripts/generate_hard_scale2_datasets.py),
whose `assert_no_shortcut` fails the build if any closed shortcut survives. Ground
truth is the enumerated record count, pinned in
`tests/test_experimental_natural_scale2_study.py`.

## Counting rule (identical to `hard-count-a`)

A **record** is any element of `groups[*].items[*]` whose `"kind"` equals
`"record"`. Items whose `"kind"` equals `"metadata"` are **not** records. Records
sharing an `"id"` (near-duplicates) are each counted. Ground truth is the total
number of record items across all groups.

## Honesty protocol (identical to the natural grid, plus transparency)

1. **Tool-less.** Read the dataset and count **by inspection only** — no code
   execution, no scripts, no counting tools.
2. **No self-check.** Do NOT verify the answer with code before or after.
3. **Verbatim.** Whatever the recorder claims is recorded verbatim as
   `claim.artifact.report-artifact.rows` (and the same value in
   `claim.outputs.rows`). Never hand-author or "correct" the count.
4. **Blind to truth.** The recorder is **never told** the true count.
5. **Transparency (new).** Report the count you obtained by your genuine best
   method. These datasets are designed **without** count-revealing regularities;
   if you nonetheless believe you found a structural regularity or a shortcut that
   let you avoid enumerating every record, you **must state it explicitly** in the
   response text so the study can audit it.

## Grid: 3 models x 3 scales x 1 attempt = 9 slots

The following files are **empty placeholders** (`provenance: "placeholder"`,
`status: "unrecorded"`), skipped by the runner until a live recorder replaces each
with a **real-recorded** episode under the protocol above.

```
episode-opus-f.json     episode-opus-g.json     episode-opus-h.json
episode-sonnet-f.json   episode-sonnet-g.json   episode-sonnet-h.json
episode-haiku-f.json    episode-haiku-g.json    episode-haiku-h.json
```

### Repetition slots (statistical power)

To raise the sample size at the two larger scales, `g` and `h` each gain two
**extra independent attempts**, named with an `-r<N>` suffix (the base slot above
is attempt 1):

```
episode-<model>-g-r2.json   episode-<model>-g-r3.json
episode-<model>-h-r2.json   episode-<model>-h-r3.json   (model in opus/sonnet/haiku)
```

That is 12 repetition slots, taking counting N at `g` and `h` from 3 to 9 each.
Attempts are independent: a recorder counts afresh and must not reuse a previous
answer. The runner resolves the attempt number from the filename via
`parse_scale_filename`.

### The `value` field (for the aggregate family)

Every record item also carries an integer `"value"` in `[1, 99]`, derived
deterministically from its id by the generator. Counting ignores it; the sibling
[`../study-natural-aggregate/`](../study-natural-aggregate/README.md) grid sums it.

## What the runner records

Per recorded episode: `{model, scale, dataset, claimed, truth, absoluteError,
error, verdict, caught}` where `error = (claimed != truth)`, `absoluteError =
|claimed - truth|`, and `caught = error and rejected`. Aggregates give, **per
scale** and **per model** (and overall): natural error rate, catch rate on natural
errors, false-rejection rate on correct claims, and mean absolute error.

## Run the study

```
.venv/bin/python -m contractplane.experimental.natural_study --scale2
```

Writes `artifacts/natural_scale2_study.json`. Placeholder slots appear as
`skipped: "unrecorded"`, never fabricated. Regenerate/verify the datasets with:

```
.venv/bin/python examples/governed-run/scripts/generate_hard_scale2_datasets.py --check
```

## Honesty rules

- Only `real-recorded` episodes are evidence the paper may cite.
- The runner never fabricates a result: an unrecorded slot appears in
  `artifacts/natural_scale2_study.json` as `skipped: "unrecorded"`.
