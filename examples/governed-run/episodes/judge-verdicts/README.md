# LLM-as-judge verifier baseline (EXPERIMENTAL)

This grid records an **LLM-as-judge** verifier applied to the nine natural scale2
producer claims, as a fair baseline against the recomputation verifier.

## Why this baseline

Reviewers call the recomputation-vs-schema-guard result "definitional": a
structural output guard *cannot*, by construction, catch a schema-valid numeric
error, so its 0/4 on the natural near-misses is a tautology. An LLM judge is a
non-definitional baseline — it is **not** blind to value errors by construction:
it can, in principle, read the dataset and recount. But it may also share the
producer's tool-less failure mode and wave a near-miss through. Whether it catches
the four natural errors (three of them off-by-one) is a genuinely open empirical
question. This grid measures the answer instead of assuming it.

## Judge condition (mirrors the producer condition)

The judge model is given:

- the producer's **claim** (the claimed row count),
- the **dataset path** (`datasets/hard-count-<f|g|h>.json`), and
- the documented **counting rule** (the same nested-groups rule the producer used).

It must decide `accept` / `reject` by **reading the dataset tool-less** — no code
execution, no scripts, no counting tools, exactly the condition the producer
worked under. It records its verdict, its own recount if it makes one, and a
rationale. The judge is **never told the true count**. Whatever it decides is
recorded verbatim; it must not self-correct with code.

## Fixture format

One file per judgment, `judge-<judgemodel>-on-<producer>-<dataset>.json`
(`<dataset>` is the `f`/`g`/`h` scale token):

```json
{
  "schema": "contractplane.dev/experimental/judge-verdict/v0",
  "provenance": "real-recorded",
  "condition": "llm-judge-tool-less",
  "judgeModel": "<judge model id>",
  "producer": "opus|sonnet|haiku",
  "dataset": "hard-count-<f|g|h>",
  "claimedRows": <the producer's claim shown to the judge>,
  "verdict": "accept" | "reject",
  "judgeRecount": <int or null>,
  "rationale": "<why the judge accepted/rejected>"
}
```

Committed files with a `pending*` judge token are **empty placeholders**
(`provenance: "placeholder"`, `status: "unrecorded"`, `verdict: null`). The scorer
**refuses to score** a placeholder — it appears as `skipped: "unrecorded"`, never
as a fabricated verdict.

### Judge model is recorded by the live agent; rename convention

The judge model is **not** fixed by the placeholder — it is recorded by the live
judge agent. A tier's placeholders use a `pending` token in the filename; when the
agent records a verdict it sets `judgeModel` in the fixture and **renames** the
file from `judge-<pending-token>-on-<producer>-<scale>.json` to
`judge-<judgemodel>-on-<producer>-<scale>.json`. The scorer keys everything off
the producer and scale (which never change) and reads the judge model from the
fixture body, so a rename is optional but conventional.

## Grid: 3 judge models x 3 producers x 3 scales = 27 slots

Three judge tiers each cover the same nine producer claims:

| filename token | judge model | status |
|---|---|---|
| `pending`  (or its recorded name `claude-opus-4-8`) | opus judge | first tier |
| `pending2` | sonnet judge (`claude-sonnet-5`) | awaiting recording |
| `pending3` | haiku judge (`claude-haiku-4-5`) | awaiting recording |

```
judge-<tier>-on-opus-f.json     judge-<tier>-on-opus-g.json     judge-<tier>-on-opus-h.json
judge-<tier>-on-sonnet-f.json   judge-<tier>-on-sonnet-g.json   judge-<tier>-on-sonnet-h.json
judge-<tier>-on-haiku-f.json    judge-<tier>-on-haiku-g.json    judge-<tier>-on-haiku-h.json
```

Each placeholder carries `producer`, `dataset`, `claimedRows`, `datasetPath`, the
judge `task` (rule + protocol), and an `intendedJudgeModel` hint — everything the
judge needs except the answer. The `pending2`/`pending3` tiers are filled by the
sonnet and haiku judge agents respectively.

## Scoring

```
.venv/bin/python -m contractplane.experimental.judge_study
```

Writes `artifacts/llm_judge_comparison.json`: per claim `{producer, dataset,
claimed, truth, error, judgeVerdict, judgeCorrect, judgeRecount}` where
`judgeCorrect` means the judge rejected exactly the erroneous claims. Aggregates
report, **per judge model**, the catch rate on the four natural errors (with an
off-by-one breakdown), the false-rejection rate on the five correct claims, and
**recount accuracy** — how often the judge's own count equals the truth, which
reveals whether a judge shares the producer's tool-less failure mode. A combined
table puts each judge model **side by side** with the schema guard (0/4 by
construction) and recomputation (4/4). Placeholder slots skip honestly, and the
`judgeRoster` shows each tier's recording progress.

## Honesty rules

- Only `real-recorded` judgments are evidence. Placeholders are skipped, never
  scored.
- The judge is never told the true count; its verdict is recorded verbatim.
- Do NOT record judgments by hand — a separate live judge agent produces them.
