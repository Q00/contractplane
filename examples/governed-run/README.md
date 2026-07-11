# governed-run (EXPERIMENTAL)

A minimal but **real** end-to-end governed execution slice. It is a research
prototype under [`contractplane.experimental`](../../src/contractplane/experimental/),
**not** part of the specified ContractPlane v1alpha1 surface. Every module it
uses is labelled experimental in its docstring.

## What this demonstrates

The frozen transition kernel (`contractplane.state`) deliberately never invokes a
capability binding, never evaluates conditions, and never mints a verdict — it
only records shape-gated events. This slice adds the consumers that turn those
contracts into an actually-governed run, driving the kernel through its public
transitions only:

1. **Executable local-process adapter** — the first code that *consumes* a
   compiled `binding`. It dispatches a stage's work as a real local subprocess
   inside a confined workspace and reads back the producer's claimed outputs.
2. **Recomputation-based independent verifier** — a separate component that, for
   mechanically recomputable evidence, derives the checked quantity **from the
   raw input data itself** (here, the row count from the caller-owned dataset)
   and compares the producer's claim against that independently computed ground
   truth. A schema check alone would only prove the producer-authored artifact is
   well-shaped; recomputation proves it is *true*. A producer that overclaims
   (`rows: 100` when the dataset holds 3) passes schema but is rejected here, and
   only an accepted verdict is fed to the kernel's `evidence.recorded` transition.
3. **Deny-by-default authority** — a stage whose declared authority exceeds its
   grant (external side effects with no external grant) is denied *pre-dispatch*
   through the kernel's existing authorization gate and recorded in the ledger;
   no work is dispatched.
4. **LLM producer-episode replay** — a recorded LLM transcript can be replayed
   deterministically offline through the *same* governed path (dispatch → claim →
   recompute-verify → verdict), so genuine agentic output is governed without a
   live API call. See [`episodes/README.md`](episodes/README.md).

## Run it

Deterministic and offline, from the repo root:

```
.venv/bin/python examples/governed-run/run_demo.py
```

It drives five governed runs, each in a fresh temporary workspace and ledger:

| # | scenario           | input                     | outcome                                            |
|---|--------------------|---------------------------|----------------------------------------------------|
| 1 | happy path         | `dataset: weekly-metrics` | recomputed row count matches -> accepted, succeeded |
| 2 | verifier rejection | `dataset: empty-dataset`  | `rows: 0` fails the evidence schema -> unit failed |
| 3 | fabrication        | fabricated `rows: 100`    | passes schema, contradicts recomputation -> rejected |
| 4 | authority denial   | publish, no grant         | external denied pre-dispatch -> run failed         |
| 5 | granted authority  | publish, external grant   | same stage authorized -> run succeeded             |

Replay a recorded producer episode instead:

```
.venv/bin/python examples/governed-run/run_demo.py --episode examples/governed-run/episodes/episode-synthetic-smoke.json
```

## Layout

- `domainpack.yaml` — the demo domain pack (validates with `contractplane validate`).
- `datasets/*.json` — caller-owned ground-truth data the verifier recomputes from.
- `workers/compile_report.py` — honest local-process worker for the `compile` stage.
- `workers/compile_report_fabricator.py` — adversarial probe worker that overclaims.
- `workers/publish_report.py` — worker for the `publish` stage (only reached when
  external authority is explicitly granted).
- `episodes/` — producer-episode fixtures and their format/honesty rules.
- `run_demo.py` — the end-to-end driver (`--episode` replays a transcript).

The same behaviour is asserted by `tests/test_experimental_governed_run.py`.

## What this slice does NOT prove

Recomputation gives genuine independence only for evidence a deterministic
function can re-derive; the typed independence spectrum (distinct-model and human
verifiers, non-recomputable evidence) remains specified-only. The slice exercises
singleton stages with local, in-workspace work and JSON/artifact evidence only.
It does **not** demonstrate `fanout: each` expansion, remote or sandboxed
adapters, semantic-review evidence, or cross-process verifier isolation. The
`synthetic-smoke` episode fixtures are hand-authored for tests and must not be
cited; only `real-recorded` episodes are evidence. It shows the governance loop
closes on the kernel; it does not show the full architecture is complete or secure.
