# composite-baseline (EXPERIMENTAL)

A head-to-head, runnable comparison between **ContractPlane** and a **composite
of off-the-shelf parts** — a CWL workflow engine + OPA/Rego policy + PROV-style
provenance — governing the *same* scenario. It exists to answer the reviewer
objection that ContractPlane's delta over such a composite is "asserted, never
shown." Everything here is runnable; every outcome comes from a real tool's exit
code, not from narration.

> This is a research comparison under `examples/`, not part of the specified
> ContractPlane v1alpha1 surface. It is labelled experimental throughout.

## The tools are real (no substitutes)

| role | tool | version |
|---|---|---|
| workflow engine | `cwltool` (in `.ouroboros/composite-venv`) | 3.2.x |
| policy engine | `opa` (`opa eval`, from PATH) | 1.18.2 |
| validator (ContractPlane side) | `contractplane validate` (repo `.venv`) | — |

No component was faked. If `opa` is absent the policy gate exits with an error
rather than pretending to pass; if `cwltool` is absent the tests skip.

## The shared scenario

Identical to [`examples/governed-run`](../governed-run): a producer counts the
records in a caller-owned dataset and **claims** a count; the claim must clear a
schema check and an **independent recomputation** of the count from the dataset
itself; an external publish requires **explicit authority**. Both sides are
driven by the **same recorded producer claims** — the `sonnet` row of
[`../governed-run/episodes/study/`](../governed-run/episodes/study/) (the claim
values are lifted verbatim into [`claims/`](claims/) and cited there) — so any
difference in outcome is a property of the governance mechanism, not the producer.

## The composite pipeline

A real CWL workflow, [`workflow/report-governed.cwl`](workflow/report-governed.cwl):

```
producer  ->  schema-gate  ->  independent-verify  ->  policy-gate (OPA)  ->  PROV log
(replay)      JSON Schema      recompute row count      Rego deny-by-default   W3C PROV JSONL
```

Each step is a CWL `CommandLineTool` wrapping a small Python script in
[`tools/`](tools/); a failing gate exits non-zero, which cwltool turns into a
`permanentFail` — a **red pipeline == a rejected run**, a fully green run ==
accepted. The schema comes first so a format-violation is caught before
recomputation, mirroring the layered check on the ContractPlane side.

## Run it

```bash
# the whole comparison (writes artifacts/composite_comparison.json + experiments.jsonl rows)
.venv/bin/python examples/composite-baseline/run_composite.py

# one condition by hand through the real engine
.ouroboros/composite-venv/bin/cwltool examples/composite-baseline/workflow/report-governed.cwl \
  --claim   examples/composite-baseline/claims/sonnet-overclaim.claim.json \
  --schema  examples/composite-baseline/schema/report-artifact.schema.json \
  --dataset examples/governed-run/datasets/monthly-metrics.json \
  --effect  examples/composite-baseline/effects/local-report.effect.json
```

Asserted by [`tests/test_composite_baseline.py`](../../tests/test_composite_baseline.py).

## Result: the four conditions

Correctly configured, the composite reproduces ContractPlane's outcomes exactly.
Both sides catch every false claim.

| condition | true rows | claimed | ContractPlane | composite (correct) | composite (misconfigured) |
|---|---|---|---|---|---|
| correct          | 3  | 3   | accepted | accepted | accepted |
| overclaim        | 12 | 999 | **rejected** (recompute) | **rejected** (verify) | ⚠️ **accepted** |
| borderline       | 7  | 8   | **rejected** (recompute) | **rejected** (verify) | ⚠️ **accepted** |
| format-violation | 3  | 3*  | **rejected** (schema)    | **rejected** (schema-gate) | **rejected** (schema-gate) |

\* correct row count, but the required `generatedBy` field is omitted.

## The delta: one realistic omission

The reviewer's real question is not "can the composite be built correctly" (it
can) but "what happens when it isn't." So we introduce the **same single drift**
on each side: drop the independent verification.

- **Composite** — [`workflow/report-misconfigured.cwl`](workflow/report-misconfigured.cwl)
  is `report-governed.cwl` with the `verify` step deleted (a realistic
  copy-paste / refactor omission). It is still **valid CWL**. It parses,
  type-checks, and runs **fully green**. The overclaim (999 vs 12) clears the
  schema gate — it is a well-shaped integer ≥ 1 — and with no recomputation left
  to contradict it, is **accepted** and written into the PROV log as a satisfied
  run. **Nothing signals that a governance step is missing.**

- **ContractPlane** — [`contractplane_omission/pack-omitted-verification.yaml`](contractplane_omission/pack-omitted-verification.yaml)
  is the governed report pack with the equivalent omission: the compile stage
  drops `requiresEvidence`. `contractplane validate` **rejects it before anything
  runs**:

  ```json
  {"error": "DomainPackValidationError",
   "issues": [{"message": "'requiresEvidence' is a required property",
               "path": "$.flows[0].stages[0]"}],
   "valid": false}
  ```

  The otherwise-identical [`pack-coupled-control.yaml`](contractplane_omission/pack-coupled-control.yaml)
  (which keeps the coupling) validates cleanly — isolating the rejection to the
  single dropped coupling.

That is the **"defaults and typed coupling"** delta, made measurable: on the
composite side, governance is an assembly of independent steps the integrator
must remember to wire and keep wired; a dropped step degrades silently to green.
On the ContractPlane side, the evidence coupling is a typed property the schema
requires, so the same omission is a *static* error, not a *runtime* surprise.

## The hardened rebuttal: "just add a Rego constraint"

A reviewer's sharp objection: OPA/Rego exists to enforce invariants like *"no
accept without a preceding verify verdict"* — write one such constraint and the
composite catches the omission too, collapsing the delta to "one file vs five."
We built and ran exactly that (`workflow/report-hardened.cwl`,
`policy/meta_accept.rego`, `tools/verify_attest.py` + `tools/accept_gate.py`;
driver `run_hardened.py`, `hardened_variant` in the comparison JSON). The honest
result, both directions:

**The meta-policy does catch the naive omission — the reviewer is right that far.**
- With the accept-gate's receipt **type-coupled** to the verify step, deleting
  verify makes **cwltool's own loader reject the workflow** at validate time,
  before any run: `Field 'source' references unknown identifier 'verify/receipt'`
  (`report-hardened-omitverify.cwl`). This is directly analogous to the pack
  validator's "references unknown evidence."
- With a **loose** receipt input, an honest "no verification" receipt is
  **denied** by the accept-gate at runtime (`report-hardened-loose.cwl`).

**But it does not collapse the delta — a second-order drift re-opens the hole.**
Both variants below **load and run green, accepting the overclaim**:
- **Drop the guard** (`report-hardened-noguard.cwl`): to remove verify you must
  also remove the now-dangling accept-gate; nothing requires a workflow to
  contain a gate, so the natural refactor deletes both and fails open.
- **Forge the receipt** (`report-hardened-forged.cwl`): keep the accept-gate,
  drop verify, and source the receipt from a producer-side attester. The gate is
  **present and consulted**, yet passes — the meta-policy can check a receipt's
  verdict and artifact binding but **not its origin**. (In the correct wiring the
  receipt comes from the verifier, which CWL isolates, so it is *not* forgeable
  there; forgeability is a property of the receipt's source, which nothing
  constrains.)

**Where each side's enforcement lives, and what must drift to fail open:**

| | hardened composite | ContractPlane |
|---|---|---|
| invariant lives in | the assembled workflow **topology** (which steps exist; where the receipt is sourced) | the stage's **type** (`requiresEvidence`) + the frozen kernel that only records evidence on an accepted verdict |
| static safety net | cwltool rejects wiring you wrote wrong (dangling source) — but has **no schema over the governance topology itself** | validator rejects a stage missing `requiresEvidence` (**exit 2, pre-run**); the unsafe stage is *unrepresentable* |
| to fail open you… | delete the guard, or re-source its receipt — **a silent edit that still validates** → green run | trip the validator (exit 2), or **tamper with the trusted kernel** — not a silently-valid config |

**Honest verdict.** The meta-policy **narrows** the delta but does not collapse
it to "one file vs five files." Correctly wired, the hardened composite genuinely
enforces the invariant, and cwltool even catches the naive verify-omission
pre-run. The residual, load-bearing delta is **"an unsafe configuration you
cannot express vs a guard whose presence and trust-wiring nothing enforces — a
guard that itself needs guarding."** The composite's real win here is that
cwltool's structural validation catches the type-coupled omission for free.

## Integration surface (measured, both directions)

Mechanically counted from the actual files (see
[`artifacts/composite_comparison.json`](../../artifacts/composite_comparison.json)),
for the **user-authored** governed behavior only:

| | composite | ContractPlane |
|---|---|---|
| files | 17 | 1 |
| distinct languages / config formats | 5 (CWL·Python·Rego·JSON Schema·JSON) | 1 (DomainPack YAML) |
| non-blank LOC | 477 | 302 |
| when a dropped governance step is caught | at runtime (or never) | at validation, before any run |

Read this **fairly**: both sides lean on library engines (cwltool + opa vs the
ContractPlane kernel), and the ContractPlane recomputer is a library component
while the composite's verify step is user-authored. The 302 LOC pack also covers
the publish and adversarial-probe flows, so the report-only subset is smaller.
The load-bearing difference is not the raw LOC but that the composite must keep
schema, policy, verification, and step-wiring **mutually consistent by hand
across five formats**, whereas the pack states the same behavior as one
declarative, statically-validated document.

## What the composite does better (a fair comparison must say so)

- **Mature, standardized ecosystem.** CWL is an open standard with multiple
  conformant engines (cwltool, Toil, Arvados); OPA/Rego is a CNCF-graduated
  policy engine with a large rule ecosystem. ContractPlane's kernel is a single
  research prototype.
- **Scale and portability.** The CWL/OPA stack already runs distributed,
  containerized, and HPC/cloud workloads with caching, retries, and provenance at
  production scale; the experimental ContractPlane slice does not attempt this.
- **Separation of concerns and staff familiarity.** Validation, policy,
  orchestration, and provenance are independent, individually swappable,
  widely-understood components with existing tooling.

## Honest caveats

- The composite here is arguably shown in a **favorable** light: its gates are
  wired correctly by hand, its verify step is a purpose-built recompute, and its
  schema/policy are hand-mirrored from the ContractPlane contract — a real
  integrator authors and maintains all of that themselves.
- Both sides exercise only singleton local stages with JSON evidence. Neither
  side's harder cases (fanout, remote/sandboxed adapters, semantic-review
  evidence) are demonstrated here.
- Only the `sonnet` recorded claims are used; they are cited in `claims/`. This
  is a mechanism comparison, not a model study.
