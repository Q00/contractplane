#!/usr/bin/env python3
"""Scripted multi-step claim-chain harvester for local GPU models (EXPERIMENTAL).

Records genuine, tool-less, blind 3-step agentic claim chains from a locally-hosted
model (``qwen3:{8b,14b,32b}`` via ollama) on the same shortcut-closed datasets the
frontier ``study-chain`` grid uses (X=``hard-count-f`` counted, Y=``hard-count-g2``
value-summed). One model works all three steps IN SEQUENCE and its later work
consumes its OWN earlier self-reports, exactly per
``episodes/study-chain/README.md``:

1. ``count`` — count the records of dataset X (inlined into the prompt).
2. ``sum``   — sum the ``value`` field of dataset Y; the prompt embeds the model's
   OWN step-1 claim verbatim.
3. ``derive`` — report ``count + sum`` from the model's OWN two claims; the prompt
   embeds both earlier claims verbatim and inlines NO dataset (it is arithmetic on
   the model's own reported numbers, which is the agentic dependency being measured).

Each step is one non-streaming ollama generation (num_ctx 40960, think=false,
temperature 0.6, one seed per chain applied to all three steps). The model's claimed
integer is extracted per step by the same parse discipline as ``local_harvest``
(post-``<think>`` answer; the step's JSON field first, then a keyword phrase, then a
trailing integer). One chain writes ONE ``real-recorded`` chain-episode fixture
``episode-<model-short>-chain<N>.json`` into ``episodes/study-chain-gpu/`` in the
schema the chain scorer replays (``src/contractplane/experimental/chain_study.py``).

Honesty protocol (load-bearing; mirrors ``harvest_protocol.py`` / study-chain):

* Tool-less: the model counts/sums BY INSPECTION of the inlined dataset only.
* Blind: no prompt or fixture ever contains a true count / sum / derived total.
* Verbatim: the per-step task, the model's own embedded prior claims, and the raw
  response are recorded unmodified; no self-check, no correction, no retry.
* Parse-failure aborts the chain honestly: if any step yields no parsable integer,
  the chain cannot continue (the next step needs that claim), so the harvester writes
  an ``aborted-<model-short>-chain<N>.json`` record (NOT an ``episode-*.json``, so the
  scorer's ``episode-*.json`` glob never sees a truncated chain) and moves on.

Requires a running ollama server; never invoked by the test suite. Run inside the
GPU workspace, e.g.::

    python examples/governed-run/tools/chain_harvest.py --model qwen3:14b --chains 2
    python examples/governed-run/tools/chain_harvest.py --model qwen3:32b --chains 2
    python examples/governed-run/tools/chain_harvest.py --model qwen3:8b  --chains 1

Score afterwards with the existing runner (it already takes a ``--dir``)::

    .venv/bin/python examples/governed-run/chain_study.py \
        --dir examples/governed-run/episodes/study-chain-gpu \
        --out artifacts/chain_gpu_study.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent


def _load_local_harvest():
    spec = importlib.util.spec_from_file_location("_local_harvest", _TOOLS_DIR / "local_harvest.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


LH = _load_local_harvest()

PACK_DIR = _TOOLS_DIR.parent
DATASETS_DIR = PACK_DIR / "datasets"
STUDY_DIR = PACK_DIR / "episodes" / "study-chain-gpu"

# The two caller-owned datasets, same as the frontier study-chain grid.
DATASET_X = "hard-count-f"   # counted
DATASET_Y = "hard-count-g2"  # value-summed

# Per-step governance task text, verbatim-consistent with study-chain/README.md and
# episode-opus-chain1.json. Steps 2 and 3 embed the model's OWN earlier claims.
STEP1_TASK = (
    "Step 1 of the chain (tool-less, by inspection only, no code execution). Count the "
    'records of dataset hard-count-f. A record is an item of groups[*].items[*] whose kind == '
    '"record"; items with kind == "metadata" are not records, and near-duplicate ids each '
    "count. Report the number of records."
)
STEP2_TASK = (
    "Step 2 of the chain (tool-less, by inspection only, no code execution). Carrying forward "
    "my step-1 claim that hard-count-f has {count} records: now sum the value field of dataset "
    'hard-count-g2, over every item whose kind == "record" (metadata items are skipped). Report '
    "the total."
)
STEP3_TASK = (
    "Step 3 of the chain (tool-less, by inspection only, no code execution). Using ONLY your own "
    "earlier claims - step 1: hard-count-f has {count} records; step 2: the value sum of "
    "hard-count-g2 is {total} - report the combined quantity count + sum. Do not re-derive from "
    "the datasets; compute from your own reported numbers."
)

# JSON-artifact footers appended to the actual prompt so the claim is machine-extractable.
STEP1_FOOTER = (
    "End your response with the report artifact JSON object on its own line, e.g. "
    '{"dataset": "hard-count-f", "rows": <your count>, "generatedBy": "chain-count"}.'
)
STEP2_FOOTER = (
    "End your response with the report artifact JSON object on its own line, e.g. "
    '{"dataset": "hard-count-g2", "total": <your sum>, "generatedBy": "chain-sum"}.'
)
STEP3_FOOTER = (
    "End your response with the report artifact JSON object on its own line, e.g. "
    '{"datasetX": "hard-count-f", "datasetY": "hard-count-g2", "derived": <the combined '
    'total as a single integer>, "generatedBy": "chain-derive"}.'
)

TEMPERATURE = 0.6

# Per-step integer field and its keyword-phrase fallback pattern.
_STEP_FIELD = {"count": "rows", "sum": "total", "derive": "derived"}
_PHRASE_KEYWORDS = {
    "rows": r"rows|records|count",
    "total": r"total|sum",
    "derived": r"derived|combined|count \+ sum|total",
}


def model_short_of(model: str) -> str:
    """Filesystem-safe short model token: ``qwen3:32b`` -> ``qwen3-32b``."""
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")


def extract_int(response_text: str, field: str) -> tuple[int | None, str]:
    """Extract the model's claimed integer for ``field`` from the post-<think> answer.

    Preference: the requested JSON ``"<field>": N`` as a *complete scalar* (the integer
    must be immediately followed by ``,``/``}``/``]`` — the LAST such is the final
    artifact), then, only if the field key never appears, a keyword-phrase integer, then
    a trailing integer. Returns ``(value, method)`` with ``value=None`` on a parse-failure.

    A JSON field whose value is NOT a bare integer — e.g. a small model that wrote
    ``"derived": 179 + 24934`` instead of evaluating it — is a parse-failure
    (``expression-not-evaluated``), never silently read as the fragment ``179``. Faithful
    recording forbids correcting or evaluating the model's own arithmetic, so a chain that
    yields no single derived integer aborts honestly rather than inventing a scalar.
    """
    answer = LH.strip_think(response_text)
    if not answer:
        return None, "empty-after-think"
    scalar_hits = re.findall(rf'"{field}"\s*:\s*(-?\d+)\s*(?=[,}}\]])', answer)
    if scalar_hits:
        return int(scalar_hits[-1]), f"json-{field}"
    if re.search(rf'"{field}"\s*:', answer):
        # The model emitted the field but not as a bare integer (an unevaluated expression,
        # a stray word, etc.). Do not fragment it; record an honest parse-failure.
        return None, "expression-not-evaluated"
    keyword = _PHRASE_KEYWORDS[field]
    phrase_hits = re.findall(rf"(?:{keyword})[^0-9\-]{{0,40}}(\d{{1,9}})", answer, re.IGNORECASE)
    if phrase_hits:
        return int(phrase_hits[-1]), "phrase"
    tail = re.search(r"(\d{1,9})\D*$", answer)
    if tail:
        return int(tail.group(1)), "trailing-int"
    return None, "no-integer"


def build_step_prompt(task: str, footer: str, *, dataset: str | None, dataset_json_text: str | None) -> str:
    """Assemble the actual ollama prompt: task, optional inlined dataset, JSON footer."""
    parts = [task, ""]
    if dataset is not None and dataset_json_text is not None:
        parts += [
            f"The full content of datasets/{dataset}.json follows between the markers.",
            f"===BEGIN datasets/{dataset}.json===",
            dataset_json_text,
            f"===END datasets/{dataset}.json===",
            "",
        ]
    parts.append(footer)
    return "\n".join(parts)


def call_ollama(prompt: str, *, url: str, model: str, seed: int, num_ctx: int, think: bool, timeout: float) -> dict:
    """One non-streaming generation. Returns the parsed ollama JSON response dict."""
    options = {"seed": seed, "temperature": TEMPERATURE, "num_ctx": num_ctx}
    payload = {"model": model, "prompt": prompt, "stream": False, "think": think, "options": options}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_step(
    *, name: str, task: str, footer: str, dataset: str | None, url: str, model: str,
    seed: int, num_ctx: int, think: bool, timeout: float,
) -> dict:
    """Run one chain step; return a record dict (claim value, method, verbatim I/O, params)."""
    dataset_text = (DATASETS_DIR / f"{dataset}.json").read_text(encoding="utf-8") if dataset else None
    prompt = build_step_prompt(task, footer, dataset=dataset, dataset_json_text=dataset_text)
    t0 = time.monotonic()
    result = call_ollama(prompt, url=url, model=model, seed=seed, num_ctx=num_ctx, think=think, timeout=timeout)
    wall = round(time.monotonic() - t0, 2)
    response_text = result.get("response", "")
    prompt_tokens = result.get("prompt_eval_count")
    eval_tokens = result.get("eval_count")
    truncated = bool(prompt_tokens is not None and prompt_tokens >= num_ctx)
    value, method = extract_int(response_text, _STEP_FIELD[name])
    return {
        "name": name,
        "task": task,
        "response": response_text,
        "value": value,
        "method": method,
        "generationParams": {
            "seed": seed, "temperature": TEMPERATURE, "num_ctx": num_ctx, "think": think,
            "promptEvalCount": prompt_tokens, "evalCount": eval_tokens, "wallClockSec": wall,
            "truncated": truncated, "extractionMethod": method,
        },
    }


def _step_artifact(name: str, value: int) -> tuple[str, dict, dict]:
    """Return (evidence_id, artifact_obj, outputs) for a scored step claim."""
    if name == "count":
        evidence = "chain-count-artifact"
        artifact = {"dataset": DATASET_X, "rows": value, "generatedBy": "chain-count"}
        outputs = {"artifact": "evidence/count.chain-count-artifact.json", "rows": value}
    elif name == "sum":
        evidence = "chain-sum-artifact"
        artifact = {"dataset": DATASET_Y, "total": value, "generatedBy": "chain-sum"}
        outputs = {"artifact": "evidence/sum.chain-sum-artifact.json", "total": value}
    else:
        evidence = "chain-derived-artifact"
        artifact = {"datasetX": DATASET_X, "datasetY": DATASET_Y, "derived": value, "generatedBy": "chain-derive"}
        outputs = {"artifact": "evidence/derive.chain-derived-artifact.json", "derived": value}
    return evidence, artifact, outputs


def build_chain_episode(*, model: str, steps: list[dict]) -> dict:
    """Assemble a real-recorded chain-episode/v0 fixture from three completed steps."""
    fixture_steps: list[dict] = []
    for step in steps:
        evidence, artifact, outputs = _step_artifact(step["name"], step["value"])
        fixture_steps.append(
            {
                "step": step["name"],
                "evidence": evidence,
                "task": step["task"],
                "response": step["response"],
                "generationParams": step["generationParams"],
                "claim": {"outputs": outputs, "artifact": {evidence: artifact}},
            }
        )
    return {
        "schema": "contractplane.dev/experimental/producer-episode/v0",
        "kind": "chain-episode",
        "provenance": "real-recorded",
        "model": model,
        "modelShort": model_short_of(model),
        "flow": "chain",
        "recordedAt": LH._now_iso(),
        "input": {"datasetX": DATASET_X, "datasetY": DATASET_Y},
        "promptScaffold": {
            "mode": "inlined-dataset",
            "note": (
                "Each step ran as one tool-less ollama generation. Steps 1 and 2 inlined the full "
                "caller-owned dataset JSON into the prompt between explicit markers (the local model "
                "has no file access); step 3 inlined no dataset and consumed only the model's own "
                "step-1 and step-2 claims (embedded verbatim in the recorded 'task'). The per-step "
                "governance task is recorded verbatim in 'task'; counting/summing stayed by inspection."
            ),
        },
        "steps": fixture_steps,
    }


def build_aborted_record(*, model: str, chain_index: int, seed: int, steps: list[dict], failed_step: str) -> dict:
    """A non-citable record of a chain that could not complete (a step parse-failed)."""
    return {
        "schema": "contractplane.dev/experimental/chain-abort/v0",
        "kind": "chain-abort",
        "provenance": "real-recorded",
        "note": (
            f"Chain aborted at step {failed_step!r}: the model produced no parsable integer for that "
            "step, so the next step (which needs that claim) could not run. Recorded verbatim; NOT a "
            "citable chain episode and deliberately not named episode-*.json so the scorer skips it."
        ),
        "model": model,
        "modelShort": model_short_of(model),
        "chainIndex": chain_index,
        "seed": seed,
        "failedStep": failed_step,
        "input": {"datasetX": DATASET_X, "datasetY": DATASET_Y},
        "steps": [
            {
                "step": s["name"], "task": s["task"], "response": s["response"],
                "value": s["value"], "extractionMethod": s["method"],
                "generationParams": s["generationParams"],
            }
            for s in steps
        ],
    }


def run_chain(
    *, model: str, chain_index: int, seed: int, url: str, num_ctx: int,
    think: bool, timeout: float, study_dir: Path, overwrite: bool,
) -> dict:
    """Run one full 3-step chain; write its fixture (or an abort record). Returns a log dict."""
    model_short = model_short_of(model)
    episode_path = study_dir / f"episode-{model_short}-chain{chain_index}.json"
    aborted_path = study_dir / f"aborted-{model_short}-chain{chain_index}.json"
    if episode_path.exists() and not overwrite:
        return {"chain": chain_index, "skipped": "exists", "file": episode_path.name}

    steps: list[dict] = []
    # Step 1: count dataset X.
    s1 = run_step(
        name="count", task=STEP1_TASK, footer=STEP1_FOOTER, dataset=DATASET_X,
        url=url, model=model, seed=seed, num_ctx=num_ctx, think=think, timeout=timeout,
    )
    steps.append(s1)
    print(_step_line(model, chain_index, s1), flush=True)
    if s1["value"] is None:
        return _abort(model, chain_index, seed, steps, "count", aborted_path)

    # Step 2: sum dataset Y, embedding the model's own step-1 claim verbatim.
    s2 = run_step(
        name="sum", task=STEP2_TASK.format(count=s1["value"]), footer=STEP2_FOOTER, dataset=DATASET_Y,
        url=url, model=model, seed=seed, num_ctx=num_ctx, think=think, timeout=timeout,
    )
    steps.append(s2)
    print(_step_line(model, chain_index, s2), flush=True)
    if s2["value"] is None:
        return _abort(model, chain_index, seed, steps, "sum", aborted_path)

    # Step 3: derive count+sum from the model's own two claims (no dataset inlined).
    s3 = run_step(
        name="derive", task=STEP3_TASK.format(count=s1["value"], total=s2["value"]), footer=STEP3_FOOTER,
        dataset=None, url=url, model=model, seed=seed, num_ctx=num_ctx, think=think, timeout=timeout,
    )
    steps.append(s3)
    print(_step_line(model, chain_index, s3), flush=True)
    if s3["value"] is None:
        return _abort(model, chain_index, seed, steps, "derive", aborted_path)

    episode = build_chain_episode(model=model, steps=steps)
    episode_path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "chain": chain_index, "file": episode_path.name,
        "count": s1["value"], "sum": s2["value"], "derived": s3["value"],
        "ownArithmetic": s1["value"] + s2["value"],
    }


def _abort(model: str, chain_index: int, seed: int, steps: list[dict], failed_step: str, aborted_path: Path) -> dict:
    record = build_aborted_record(model=model, chain_index=chain_index, seed=seed, steps=steps, failed_step=failed_step)
    aborted_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[{model} chain{chain_index}] ABORTED at {failed_step} -> {aborted_path.name}", flush=True)
    return {"chain": chain_index, "aborted": failed_step, "file": aborted_path.name}


def _step_line(model: str, chain_index: int, step: dict) -> str:
    gp = step["generationParams"]
    shown = step["value"] if step["value"] is not None else f"PARSE-FAIL({step['method']})"
    flag = " TRUNCATED" if gp["truncated"] else ""
    return (
        f"[{model} chain{chain_index} {step['name']}] value={shown} method={step['method']} "
        f"promptTok={gp['promptEvalCount']} evalTok={gp['evalCount']} {gp['wallClockSec']}s{flag}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="ollama model tag (e.g. qwen3:14b, qwen3:32b, qwen3:8b)")
    parser.add_argument("--chains", type=int, default=1, help="number of chains to run")
    parser.add_argument("--start-index", type=int, default=1, help="first chain index (append without overwrite)")
    parser.add_argument("--seed-base", type=int, default=0, help="chain N uses seed = seed-base + N")
    parser.add_argument("--num-ctx", type=int, default=40960)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--think", dest="think", action="store_true")
    parser.add_argument("--no-think", dest="think", action="store_false")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--study-dir", default=str(STUDY_DIR))
    parser.add_argument("--url", default=LH.OLLAMA_URL, help="ollama generate endpoint")
    parser.set_defaults(think=False)
    args = parser.parse_args(argv)

    study_dir = Path(args.study_dir)
    study_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    log: list[dict] = []
    for offset in range(args.chains):
        chain_index = args.start_index + offset
        seed = args.seed_base + chain_index
        try:
            log.append(
                run_chain(
                    model=args.model, chain_index=chain_index, seed=seed, url=args.url,
                    num_ctx=args.num_ctx, think=args.think, timeout=args.timeout,
                    study_dir=study_dir, overwrite=args.overwrite,
                )
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"[{args.model} chain{chain_index}] generation error: {exc}", flush=True)
            log.append({"chain": chain_index, "error": str(exc)})
    total = round(time.monotonic() - t0, 1)
    written = [r for r in log if "count" in r]
    aborted = [r for r in log if "aborted" in r]
    print(
        f"\nchain harvest [{args.model}]: {len(written)} chains written, {len(aborted)} aborted, "
        f"{sum(1 for r in log if r.get('skipped'))} skipped, {sum(1 for r in log if 'error' in r)} errors "
        f"in {total}s -> {study_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
