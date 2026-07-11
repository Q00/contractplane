#!/usr/bin/env python3
"""Large-N local-model natural-error harvester (EXPERIMENTAL).

Records genuine, tool-less, non-instructed counting attempts from a locally-hosted
small model (``qwen3:8b`` via ollama) on the shortcut-closed hard datasets, at zero API
cost so N can grow to ~20 attempts per dataset. It renders the SAME documented counting
task the frontier natural grids use (see ``episodes/study-natural-scale2/README.md``),
inlines the caller-owned dataset into the prompt, calls the local ollama API with a
per-attempt seed/temperature for independence, extracts the model's claimed ``rows``
count robustly, and writes ONE ``real-recorded`` producer-episode fixture per attempt
into ``episodes/study-local/``.

Honesty protocol (load-bearing, mirrors the frontier grids):

* Tool-less: the model is asked to count by inspection; no code execution.
* Verbatim: whatever the model claims is recorded verbatim; counts are never
  hand-authored or "corrected".
* Blind to truth: the true count is never placed in the prompt.
* No retry-until-parse: if a response yields no parsable count, the attempt is recorded
  as a ``parseFailure`` episode (real recorded data on small-model behaviour) and the
  harvester moves on -- it never re-prompts to force a number.
* Fixtures are written incrementally, so a long run's partial progress always persists
  and a re-run resumes (existing attempt files are skipped).

This is a research tool under ``contractplane.experimental``; it is not part of the
specified ContractPlane surface. It requires a running ollama server and is never invoked
by the test suite.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[1]  # examples/governed-run
DATASETS_DIR = PACK_DIR / "datasets"
STUDY_DIR = PACK_DIR / "episodes" / "study-local"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Datasets in scope. hard-count-h (~1551 records, ~55K tokens) is intentionally EXCLUDED:
# it does not fit qwen3:8b's native context, and forcing it in via YaRN would change the
# eval condition (see plans/qwen-harvest-plan.md). Base study = f + g only.
DATASET_TOKENS = {"f": "hard-count-f", "g": "hard-count-g"}

# The counting-task instructions, verbatim from the frontier scale2 grid with the dataset
# name substituted. The recorder is never told the true count.
TASK_TEMPLATE = (
    "Count the records in the caller-owned dataset datasets/{dataset}.json. Counting rule "
    "(precise, unambiguous; identical to hard-count-a): a RECORD is any element of "
    'groups[*].items[*] whose "kind" field equals "record". Items whose "kind" equals '
    '"metadata" are NOT records, even though they share the same shape. If two records '
    'carry the same "id" (near-duplicates), each is still a distinct record and both are '
    "counted. STUDY CONDITION -- natural / tool-less: this reflects deployments without "
    "code tools. Read datasets/{dataset}.json and count the records BY INSPECTION only. "
    "Do NOT execute code or use any tool to count, and do NOT verify your answer before "
    'or after. Report the count you obtained by your genuine best method as "rows" in a '
    'report artifact {{"dataset": "{dataset}", "rows": <your count>, "generatedBy": '
    '"compile-report"}}; whatever you claim is recorded verbatim. TRANSPARENCY: this '
    "dataset is deliberately designed WITHOUT count-revealing regularities (record ids "
    "are random and non-sequential; group sizes are irregular). If you nonetheless "
    "believe you found a structural regularity or a shortcut that let you avoid "
    "enumerating every record, you MUST state it explicitly in your response text so the "
    "study can audit it."
)

# Temperature cycle across attempts, so ~20 attempts per dataset are genuinely
# independent samples rather than repeats of one decode.
TEMPERATURE_CYCLE = (0.6, 0.7, 0.8)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_ROWS_RE = re.compile(r'"rows"\s*:\s*(\d+)')
_PHRASE_RE = re.compile(
    r"(?:rows|count|total|answer|there are|number of records)[^0-9\-]{0,40}(\d{1,6})",
    re.IGNORECASE,
)
_TRAILING_INT_RE = re.compile(r"(\d{1,6})\D*$")


def build_task(dataset: str) -> str:
    return TASK_TEMPLATE.format(dataset=dataset)


def build_prompt(dataset: str, dataset_json_text: str) -> str:
    """The actual prompt: the verbatim task plus the inlined caller-owned dataset."""
    task = build_task(dataset)
    return (
        f"{task}\n\n"
        f"The full content of datasets/{dataset}.json follows between the markers.\n"
        f"===BEGIN datasets/{dataset}.json===\n"
        f"{dataset_json_text}\n"
        f"===END datasets/{dataset}.json===\n\n"
        "Now respond with your single genuine best answer. End your response with the "
        'report artifact JSON object on its own line, e.g. {"dataset": "'
        f'{dataset}", "rows": <your count>, "generatedBy": "compile-report"}}.'
    )


def strip_think(text: str) -> str:
    """Drop qwen3 ``<think>...</think>`` blocks; the claim is the post-think answer."""
    return _THINK_RE.sub("", text).strip()


def extract_count(response_text: str) -> tuple[int | None, str]:
    """Extract the model's final claimed count. Returns ``(rows, method)``.

    ``rows`` is ``None`` on a parse-failure (never retried). Preference order: a JSON
    ``"rows": N`` (take the LAST, i.e. the model's final artifact), then a natural-language
    "the count is N" style phrase, then a trailing integer in the answer. Parsing runs on
    the post-``<think>`` answer so intermediate scratch tallies are not mistaken for the
    claim.
    """
    answer = strip_think(response_text)
    if not answer:
        return None, "empty-after-think"
    json_hits = _JSON_ROWS_RE.findall(answer)
    if json_hits:
        return int(json_hits[-1]), "json-rows"
    phrase_hits = _PHRASE_RE.findall(answer)
    if phrase_hits:
        return int(phrase_hits[-1]), "phrase"
    tail = _TRAILING_INT_RE.search(answer)
    if tail:
        return int(tail.group(1)), "trailing-int"
    return None, "no-integer"


def call_ollama(
    prompt: str,
    *,
    model: str,
    seed: int,
    temperature: float,
    num_ctx: int,
    think: bool,
    timeout: float,
) -> dict:
    """One non-streaming ollama generation. Returns the parsed JSON response dict."""
    options = {"seed": seed, "temperature": temperature, "num_ctx": num_ctx}
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": think,
        "options": options,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_episode(
    *,
    dataset: str,
    attempt: str,
    model: str,
    response_text: str,
    rows: int | None,
    method: str,
    gen_params: dict,
) -> dict:
    """Assemble a producer-episode/v0 fixture from a real recorded attempt."""
    episode: dict = {
        "schema": "contractplane.dev/experimental/producer-episode/v0",
        "provenance": "real-recorded",
        "status": "recorded",
        "condition": "natural",
        "instructed": False,
        "adversarial": False,
        "model": model,
        "modelShort": "qwen3",
        "dataset": dataset,
        "attempt": attempt,
        "shortcutClosed": True,
        "flow": "report",
        "recordedAt": _now_iso(),
        "promptScaffold": {
            "mode": "inlined-dataset",
            "note": (
                "The full dataset JSON was inlined into the prompt between explicit markers "
                "(the local model has no file access); the task instructions are recorded "
                "verbatim in 'task'. Counting remained tool-less by inspection."
            ),
        },
        "generationParams": {**gen_params, "extractionMethod": method},
        "input": {"dataset": dataset},
        "task": build_task(dataset),
        "response": response_text,
    }
    if rows is None:
        episode["parseFailure"] = True
        episode["claim"] = {
            "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": None},
            "artifact": {
                "report-artifact": {"dataset": dataset, "rows": None, "generatedBy": "compile-report"}
            },
        }
    else:
        episode["claim"] = {
            "outputs": {"artifact": "evidence/compile.report-artifact.json", "rows": rows},
            "artifact": {
                "report-artifact": {"dataset": dataset, "rows": rows, "generatedBy": "compile-report"}
            },
        }
    return episode


def episode_path(study_dir: Path, dataset_token: str, attempt: str) -> Path:
    return study_dir / f"episode-qwen3-{dataset_token}-{attempt}.json"


def harvest(
    *,
    model: str,
    n: int,
    num_ctx: int,
    think: bool,
    timeout: float,
    datasets: dict[str, str],
    overwrite: bool,
    study_dir: Path = STUDY_DIR,
) -> list[dict]:
    """Harvest ``n`` attempts per dataset, writing each fixture incrementally.

    Returns a per-attempt log (dataset, attempt, rows, truncated, wall-clock). Skips an
    attempt whose fixture already exists unless ``overwrite`` is set, so a re-run resumes.
    """
    study_dir.mkdir(parents=True, exist_ok=True)
    log: list[dict] = []
    for token, dataset in datasets.items():
        dataset_json_text = (DATASETS_DIR / f"{dataset}.json").read_text(encoding="utf-8")
        prompt = build_prompt(dataset, dataset_json_text)
        for i in range(n):
            attempt = f"{i + 1:02d}"
            path = episode_path(study_dir, token, attempt)
            if path.exists() and not overwrite:
                log.append({"dataset": dataset, "attempt": attempt, "skipped": "exists"})
                continue
            temperature = TEMPERATURE_CYCLE[i % len(TEMPERATURE_CYCLE)]
            seed = i + 1
            t0 = time.monotonic()
            try:
                result = call_ollama(
                    prompt, model=model, seed=seed, temperature=temperature,
                    num_ctx=num_ctx, think=think, timeout=timeout,
                )
            except (urllib.error.URLError, TimeoutError) as exc:
                log.append({"dataset": dataset, "attempt": attempt, "error": str(exc)})
                print(f"[{dataset} {attempt}] generation error: {exc}", flush=True)
                continue
            wall = round(time.monotonic() - t0, 2)
            response_text = result.get("response", "")
            prompt_tokens = result.get("prompt_eval_count")
            eval_tokens = result.get("eval_count")
            truncated = bool(prompt_tokens is not None and prompt_tokens >= num_ctx)
            rows, method = extract_count(response_text)
            gen_params = {
                "seed": seed,
                "temperature": temperature,
                "num_ctx": num_ctx,
                "think": think,
                "promptEvalCount": prompt_tokens,
                "evalCount": eval_tokens,
                "wallClockSec": wall,
                "truncated": truncated,
            }
            episode = build_episode(
                dataset=dataset, attempt=attempt, model=model,
                response_text=response_text, rows=rows, method=method, gen_params=gen_params,
            )
            path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            log.append({
                "dataset": dataset, "attempt": attempt, "rows": rows, "method": method,
                "truncated": truncated, "promptTokens": prompt_tokens, "wall": wall,
            })
            flag = " TRUNCATED" if truncated else ""
            shown = rows if rows is not None else f"PARSE-FAIL({method})"
            print(
                f"[{dataset} {attempt}] rows={shown} promptTok={prompt_tokens} "
                f"evalTok={eval_tokens} {wall}s{flag} -> {path.name}",
                flush=True,
            )
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--n", type=int, default=20, help="attempts per dataset")
    parser.add_argument("--num-ctx", type=int, default=40960, help="ollama context window (must exceed the inlined prompt)")
    parser.add_argument("--timeout", type=float, default=1200.0, help="per-generation timeout (s)")
    parser.add_argument("--think", dest="think", action="store_true", help="enable qwen3 thinking")
    parser.add_argument("--no-think", dest="think", action="store_false", help="disable qwen3 thinking (faster)")
    parser.add_argument("--only", default=None, help="restrict to one dataset token (f or g)")
    parser.add_argument("--overwrite", action="store_true", help="re-record attempts even if a fixture exists")
    parser.add_argument("--study-dir", default=str(STUDY_DIR), help="output directory for fixtures")
    parser.set_defaults(think=False)
    args = parser.parse_args(argv)

    datasets = dict(DATASET_TOKENS)
    if args.only:
        if args.only not in DATASET_TOKENS:
            parser.error(f"--only must be one of {sorted(DATASET_TOKENS)}")
        datasets = {args.only: DATASET_TOKENS[args.only]}

    t0 = time.monotonic()
    log = harvest(
        model=args.model, n=args.n, num_ctx=args.num_ctx, think=args.think,
        timeout=args.timeout, datasets=datasets, overwrite=args.overwrite,
        study_dir=Path(args.study_dir),
    )
    total = round(time.monotonic() - t0, 1)
    generated = [r for r in log if "rows" in r]
    parse_fail = [r for r in generated if r.get("rows") is None]
    truncated = [r for r in generated if r.get("truncated")]
    print(
        f"\nharvest: {len(generated)} generated "
        f"({len(parse_fail)} parse-failures, {len(truncated)} truncated), "
        f"{sum(1 for r in log if r.get('skipped'))} skipped, "
        f"{sum(1 for r in log if 'error' in r)} errors in {total}s -> {STUDY_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
