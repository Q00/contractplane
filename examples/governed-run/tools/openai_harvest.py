#!/usr/bin/env python3
"""OpenAI-family natural-error harvester via Codex CLI OAuth (EXPERIMENTAL).

Sibling of ``local_harvest.py``. Records genuine, tool-less, non-instructed counting
attempts from OpenAI frontier models (Luna / Terra / Sol) served through the Codex CLI
under an OAuth subscription -- NO API key is used (house rule: OAuth-only). It renders the
SAME documented counting task the frontier natural grids and the qwen harvester use
(verbatim from ``episodes/study-natural-scale2/README.md``), inlines the caller-owned
dataset into the prompt, calls ``codex exec -m <model>`` once per attempt with a
per-attempt reasoning/temperature record, extracts the model's claimed ``rows`` count with
the SAME robust parser as the qwen harvester, and writes ONE ``real-recorded``
producer-episode fixture per attempt into ``episodes/study-openai/``.

Honesty protocol (load-bearing, identical to the qwen/frontier grids):

* Tool-less: the model is asked to count by inspection; no code execution. Codex runs
  read-only sandboxed so the model cannot shell out to count.
* Verbatim: whatever the model claims is recorded verbatim; counts are never
  hand-authored or "corrected".
* Blind to truth: the true count is NEVER placed in the prompt. Truths live only with the
  orchestrator (EXPERIMENT_HANDOFF.md §6).
* No retry-until-parse: an unparsable response is recorded as a ``parseFailure`` episode
  (real data on model behaviour); the harvester moves on, never re-prompting for a number.
* Fixtures are written incrementally, so partial progress persists and a re-run resumes.

Reasoning condition: recorded explicitly per episode (``reasoningEffort``). Matched to the
qwen GPU arm being run with thinking ENABLED, so the cross-vendor capability curve compares
like-for-like. Set deliberately via ``--reasoning``; never left implicit.

Research tool under the governed-run example pack; not part of the specified surface and
never invoked by the test suite. Requires the Codex CLI (``codex``) authenticated via OAuth.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# Reuse the qwen harvester's task text, prompt builder, parser, and episode schema so the
# ONLY difference between vendors is the generation backend (not the task or the recording).
from local_harvest import (  # noqa: E402  (sibling module in the same tools/ dir)
    DATASETS_DIR,
    build_episode,
    build_prompt,
    build_task,
    extract_count,
)

PACK_DIR = Path(__file__).resolve().parents[1]  # examples/governed-run
STUDY_DIR = PACK_DIR / "episodes" / "study-openai"

# The three OpenAI models Sergio verifies (Codex-served, OAuth). Partner (Q00) runs qwen on
# GPU with thinking on; these are the cross-vendor frontier arm.
MODELS = {
    "luna": "gpt-5.6-luna",
    "terra": "gpt-5.6-terra",
    "sol": "gpt-5.6-sol",
}

# Datasets in scope for the matched cross-vendor comparison: f + g, identical to the qwen
# base study. hard-count-h (~55K tokens) is a separate reported extension only (context fits
# for OpenAI but not qwen; never pooled across unequal coverage).
DATASET_TOKENS = {"f": "hard-count-f", "g": "hard-count-g"}
DATASET_TOKENS_EXT = {"h": "hard-count-h"}

TEMPERATURE_CYCLE = (0.6, 0.7, 0.8)


def call_codex(prompt: str, *, model: str, reasoning: str, timeout: float) -> tuple[str, dict]:
    """One Codex CLI generation over OAuth. Returns ``(final_message_text, meta)``.

    ``codex exec -m <model>`` prints the model's final message on stdout; the banner and
    logs go to stderr (dropped). Read-only sandbox keeps the count tool-less. The prompt is
    passed on stdin so large inlined datasets do not hit argv limits.
    """
    cmd = [
        "codex", "exec",
        "-m", model,
        "-c", f"model_reasoning_effort={reasoning}",
        "-s", "read-only",
        "--skip-git-repo-check",
    ]
    proc = subprocess.run(
        cmd, input=prompt, text=True, capture_output=True, timeout=timeout, check=False,
    )
    meta = {"returncode": proc.returncode, "stderrTail": proc.stderr[-500:]}
    return proc.stdout, meta


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_openai_episode(
    *, dataset: str, attempt: str, model_short: str, model_id: str,
    response_text: str, rows: int | None, method: str, gen_params: dict,
) -> dict:
    """producer-episode/v0 fixture from a real Codex-recorded attempt.

    Mirrors ``local_harvest.build_episode`` but stamps the OpenAI model id/short and an
    OAuth-substrate note; the claim/task/blinding structure is identical.
    """
    ep = build_episode(
        dataset=dataset, attempt=attempt, model=model_id,
        response_text=response_text, rows=rows, method=method, gen_params=gen_params,
    )
    ep["modelShort"] = model_short
    ep["promptScaffold"] = {
        "mode": "inlined-dataset",
        "note": (
            "The full dataset JSON was inlined into the prompt between explicit markers; "
            "the model was served via `codex exec` under OAuth (no API key) in a read-only "
            "sandbox, so counting remained tool-less by inspection. Task recorded verbatim "
            "in 'task'."
        ),
    }
    ep["task"] = build_task(dataset)
    return ep


def episode_path(study_dir: Path, model_short: str, dataset_token: str, attempt: str) -> Path:
    return study_dir / f"episode-{model_short}-{dataset_token}-{attempt}.json"


def harvest(
    *, model_short: str, model_id: str, n: int, reasoning: str, timeout: float,
    datasets: dict[str, str], overwrite: bool, study_dir: Path = STUDY_DIR,
) -> list[dict]:
    study_dir.mkdir(parents=True, exist_ok=True)
    log: list[dict] = []
    for token, dataset in datasets.items():
        dataset_json_text = (DATASETS_DIR / f"{dataset}.json").read_text(encoding="utf-8")
        prompt = build_prompt(dataset, dataset_json_text)
        for i in range(n):
            attempt = f"{i + 1:02d}"
            path = episode_path(study_dir, model_short, token, attempt)
            if path.exists() and not overwrite:
                log.append({"dataset": dataset, "attempt": attempt, "skipped": "exists"})
                continue
            temperature = TEMPERATURE_CYCLE[i % len(TEMPERATURE_CYCLE)]
            t0 = time.monotonic()
            try:
                response_text, meta = call_codex(
                    prompt, model=model_id, reasoning=reasoning, timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                log.append({"dataset": dataset, "attempt": attempt, "error": f"timeout:{exc}"})
                print(f"[{model_short} {dataset} {attempt}] timeout", flush=True)
                continue
            wall = round(time.monotonic() - t0, 2)
            if meta["returncode"] != 0 or not response_text.strip():
                # A backend failure is recorded as an error log row, not a fabricated claim.
                log.append({"dataset": dataset, "attempt": attempt,
                            "error": f"rc={meta['returncode']}", "stderrTail": meta["stderrTail"]})
                print(f"[{model_short} {dataset} {attempt}] backend error rc={meta['returncode']}", flush=True)
                continue
            rows, method = extract_count(response_text)
            gen_params = {
                "provider": "openai-codex-oauth",
                "modelId": model_id,
                "temperature": temperature,
                "reasoningEffort": reasoning,
                "think": True,
                "wallClockSec": wall,
                "returncode": meta["returncode"],
            }
            episode = build_openai_episode(
                dataset=dataset, attempt=attempt, model_short=model_short, model_id=model_id,
                response_text=response_text, rows=rows, method=method, gen_params=gen_params,
            )
            path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            log.append({"dataset": dataset, "attempt": attempt, "rows": rows, "method": method, "wall": wall})
            shown = rows if rows is not None else f"PARSE-FAIL({method})"
            print(f"[{model_short} {dataset} {attempt}] rows={shown} {wall}s -> {path.name}", flush=True)
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=sorted(MODELS),
                        help="one of luna|terra|sol (OpenAI, Codex-served)")
    parser.add_argument("--n", type=int, default=20, help="attempts per dataset")
    parser.add_argument("--reasoning", default="high",
                        help="model_reasoning_effort passed to codex (matched to qwen think-on arm)")
    parser.add_argument("--timeout", type=float, default=1200.0, help="per-generation timeout (s)")
    parser.add_argument("--only", default=None, help="restrict to one dataset token (f|g|h)")
    parser.add_argument("--include-h", action="store_true", help="add hard-count-h as a separate extension (never pooled)")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--study-dir", default=str(STUDY_DIR))
    args = parser.parse_args(argv)

    pool = dict(DATASET_TOKENS)
    if args.include_h:
        pool.update(DATASET_TOKENS_EXT)
    if args.only:
        allowed = {**DATASET_TOKENS, **DATASET_TOKENS_EXT}
        if args.only not in allowed:
            parser.error(f"--only must be one of {sorted(allowed)}")
        pool = {args.only: allowed[args.only]}

    model_id = MODELS[args.model]
    t0 = time.monotonic()
    log = harvest(
        model_short=args.model, model_id=model_id, n=args.n, reasoning=args.reasoning,
        timeout=args.timeout, datasets=pool, overwrite=args.overwrite,
        study_dir=Path(args.study_dir),
    )
    recorded = sum(1 for r in log if "rows" in r)
    skipped = sum(1 for r in log if r.get("skipped"))
    errored = sum(1 for r in log if r.get("error"))
    print(f"\n{args.model}: recorded={recorded} skipped={skipped} errored={errored} "
          f"in {round(time.monotonic() - t0, 1)}s -> {args.study_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
