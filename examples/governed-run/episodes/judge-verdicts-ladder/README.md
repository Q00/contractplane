# LLM-as-judge over the GPU-ladder near-miss corpus (EXPERIMENTAL)

This grid records an **LLM-as-judge** verifier applied to the **12 hardest**
natural miscounts from the local GPU ladder, to widen the paper's judged
natural-error corpus from 4 (the scale2 grid in `../judge-verdicts/`) to **16**.

## Why this grid

The scale2 judge grid has only four natural errors (three off-by-one) — a thin
base for the claim that a fair, non-definitional judge still waves near-misses
through. The GPU ladder (`artifacts/local_gpu_family_study.json`: qwen3:14b and
qwen3:32b on `hard-count-f`/`g`) produced dozens of natural miscounts. Its
*smallest* absolute errors are precisely the judge-challenging ones: an
off-by-one on a ~300-record dataset is the near-miss a tool-less judge is most
likely to accept. The 12 claims here are those smallest-`|error|` near-misses,
selected by the orchestrator from the recorded ladder artifact. **Every one of
the 12 is an error** (the smallest is off by one).

## Judge condition (identical to `../judge-verdicts/`)

The judge model is given:

- the producer's **claim** (`claimedRows`),
- the **dataset path** (`datasets/hard-count-<f|g>.json`), and
- the documented **counting rule** (the same nested-groups rule the producer used).

It must decide `accept` / `reject` by **reading the dataset tool-less** — no code
execution, no scripts, no counting tools, exactly the condition the producer
worked under. It records its verdict, its own recount if it makes one, and a
rationale. The judge is **never told the true count**. Whatever it decides is
recorded verbatim; it must not self-correct with code.

## Fixture format

One file per judgment, `judge-<judgemodel>-on-<episode-stem>.json`, where
`<episode-stem>` is the source producer episode stem (e.g.
`qwen3-32b-g-17` for `episode-qwen3-32b-g-17.json`):

```json
{
  "schema": "contractplane.dev/experimental/judge-verdict/v0",
  "provenance": "real-recorded",
  "condition": "llm-judge-tool-less",
  "judgeModel": "<judge model id>",
  "producerModel": "qwen3:14b|qwen3:32b",
  "dataset": "hard-count-<f|g>",
  "datasetPath": "datasets/hard-count-<f|g>.json",
  "sourceEpisode": "episode-<stem>.json",
  "claimedRows": <the producer's claim shown to the judge>,
  "verdict": "accept" | "reject",
  "judgeRecount": <int or null>,
  "rationale": "<why the judge accepted/rejected>"
}
```

Committed files with a `pending*` judge token are **empty placeholders**
(`provenance: "placeholder"`, `status: "unrecorded"`, `verdict: null`). Each
placeholder carries the producer model, the dataset name + path, the source
episode filename, `claimedRows`, and the judge `task` (rule + tool-less/blind
protocol) — everything the judge needs **except the answer**. The scorer
**refuses to score** a placeholder — it appears as `skipped: "unrecorded"`, never
as a fabricated verdict.

### Judge model is recorded by the live agent; rename convention

The judge model is **not** fixed by the placeholder — it is recorded by the live
judge agent. A tier's placeholders use a `pending` token in the filename; when the
agent records a verdict it sets `judgeModel` in the fixture body and **renames**
the file from `judge-<pending-token>-on-<stem>.json` to
`judge-<judgemodel>-on-<stem>.json`. The scorer keys everything off the episode
stem (which never changes) and reads the judge model from the fixture body, so a
rename is optional but conventional.

## Grid: 3 judge tiers x 12 near-miss claims = 36 slots

Three judge tiers each cover the same 12 producer claims:

| filename token | intended judge model | status |
|---|---|---|
| `pending`  (or its recorded name `claude-opus-4-8`) | opus judge | first tier |
| `pending2` | sonnet judge (`claude-sonnet-5`) | awaiting recording |
| `pending3` | haiku judge (`claude-haiku-4-5`) | awaiting recording |

The 12 producer claims (source episode, producer model, dataset, claim shown to
the judge). The true count is **not** listed here — the judge must derive it:

| source episode | producer | dataset | claimedRows |
|---|---|---|---|
| `episode-qwen3-14b-f-13.json` | qwen3:14b | hard-count-f | 274 |
| `episode-qwen3-14b-f-14.json` | qwen3:14b | hard-count-f | 274 |
| `episode-qwen3-32b-f-03.json` | qwen3:32b | hard-count-f | 274 |
| `episode-qwen3-14b-f-02.json` | qwen3:14b | hard-count-f | 275 |
| `episode-qwen3-32b-f-08.json` | qwen3:32b | hard-count-f | 271 |
| `episode-qwen3-14b-f-09.json` | qwen3:14b | hard-count-f | 266 |
| `episode-qwen3-32b-f-05.json` | qwen3:32b | hard-count-f | 265 |
| `episode-qwen3-32b-f-16.json` | qwen3:32b | hard-count-f | 281 |
| `episode-qwen3-32b-f-20.json` | qwen3:32b | hard-count-f | 264 |
| `episode-qwen3-32b-f-17.json` | qwen3:32b | hard-count-f | 263 |
| `episode-qwen3-32b-f-04.json` | qwen3:32b | hard-count-f | 284 |
| `episode-qwen3-32b-g-17.json` | qwen3:32b | hard-count-g | 767 |

## Scoring

```
.venv/bin/python -m contractplane.experimental.ladder_judge_study
```

Writes `artifacts/ladder_judge_study.json`. For each of the 12 claims the scorer
**replays the producer episode through the governed path** to derive the truth,
the schema-guard column, and the recomputation column (truth is never hardcoded),
then scores each recorded judge verdict — `judgeCorrect` means the judge rejected
exactly the erroneous claims. Because **all 12 claims are errors**, the
false-rejection denominator here is 0; the meaningful false-rejection evidence
stays with the scale2 corpus (5 correct claims). The combined table merges the
scale2 judged errors (4) with these ladder errors (12) into the 16-error corpus
and pools each judge model's catch rate across both. Placeholder slots skip
honestly, and the `judgeRoster` shows each tier's recording progress.

## Honesty rules

- Only `real-recorded` judgments are evidence. Placeholders are skipped, never
  scored.
- The judge is never told the true count; its verdict is recorded verbatim.
- The true count appears in **no** placeholder and **not** in this README.
- Do NOT record judgments by hand — a separate live judge agent produces them.
