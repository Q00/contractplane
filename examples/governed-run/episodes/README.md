# Producer episodes (EXPERIMENTAL)

A *producer episode* is a recorded LLM transcript that can be replayed
deterministically offline through the same governed run path as the subprocess
producer (`dispatch -> claim -> recompute-verify -> verdict`). This is how the
slice exercises genuine agentic output without a live API call in the test suite.

Replay one from the repo root:

```
.venv/bin/python examples/governed-run/run_demo.py --episode <fixture.json>
```

## Format (`contractplane.dev/experimental/producer-episode/v0`)

```json
{
  "schema": "contractplane.dev/experimental/producer-episode/v0",
  "provenance": "real-recorded",
  "adversarial": false,
  "model": "<model id>",
  "recordedAt": "<ISO-8601 or null>",
  "flow": "report",
  "input": { "dataset": "weekly-metrics" },
  "task": "<the prompt the model was given>",
  "response": "<the model's raw response text>",
  "claim": {
    "outputs": { "artifact": "evidence/compile.report-artifact.json", "rows": 3 },
    "artifact": { "report-artifact": { "dataset": "weekly-metrics", "rows": 3, "generatedBy": "compile-report" } }
  }
}
```

- `claim.outputs` is the capability claim the kernel schema-gates on `claim_unit`.
- `claim.artifact` maps each declared evidence id to the artifact the model
  produced; the runner writes it to the harness-owned evidence path, then the
  independent verifier recomputes ground truth and decides the verdict. A model
  that overclaims is rejected exactly as a live overclaiming model would be.

## Honesty rule

- **`provenance: "real-recorded"`** — actual recorded model output. These are the
  ONLY episodes the paper may cite.
- **`provenance: "synthetic-smoke"`** — hand-authored fixture used solely to
  exercise the runner in tests. The paper must **NOT** cite these.
- **Adversarial episodes** must set `"adversarial": true` and be described as
  probes, never presented as normal behavior.
- **Unrecorded slots** carry `"provenance": "placeholder"` / `"status":
  "unrecorded"`. The runner refuses to replay them, so an empty slot can never be
  passed off as evidence.

## Files

| file | status |
|---|---|
| `episode-correct.json` | **empty slot** — a live agent must record a real correct episode here |
| `episode-adversarial.json` | **empty slot** — a live agent must record a real adversarial probe here |
| `episode-synthetic-smoke.json` | synthetic-smoke, correct — test-only, not citable |
| `episode-synthetic-smoke-adversarial.json` | synthetic-smoke, adversarial — test-only, not citable |
