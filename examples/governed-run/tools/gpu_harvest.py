#!/usr/bin/env python3
"""Track B: GPU model-ladder natural-error harvester (EXPERIMENTAL).

Thin wrapper around the EXECUTED ``local_harvest.py`` so the eval condition stays
identical by construction: the task text, prompt assembly, count extraction, and
episode schema are imported from that module (whose prompt is drift-guarded against
``harvest_protocol.py`` by tests). Only condition VARIABLES change, and each is
recorded per episode in ``generationParams``: model (the ladder), think mode
(matched arm), num_ctx, optional num_predict cap (runaway-CoT guard for think=on).

Inside the GPU workspace (ollama serving locally, models pulled):

    python examples/governed-run/tools/gpu_harvest.py --model qwen3:14b --n 20
    python examples/governed-run/tools/gpu_harvest.py --model qwen3:32b --n 20
    # matched think arm (the 8B M3 run could not terminate; on GPU cap the decode):
    python examples/governed-run/tools/gpu_harvest.py --model qwen3:8b --think --num-predict 16384 --n 20

Fixtures land in ``episodes/study-local-gpu/`` as
``episode-<model-short>-<f|g>-<NN>.json``. Replay/aggregate afterwards:

    .venv/bin/python examples/governed-run/family_study_runner.py \
        --dir examples/governed-run/episodes/study-local-gpu \
        --family local-gpu --out artifacts/local_gpu_family_study.json

Honesty protocol unchanged (tool-less, blind, verbatim, parse-failure-as-data);
truths are commit-reveal sealed in ``seals/seal-2026-07-12-trackAB.json`` BEFORE
any recording here.
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
STUDY_DIR = PACK_DIR / "episodes" / "study-local-gpu"


def model_short_of(model: str) -> str:
    """Filesystem-safe short model token: ``qwen3:32b`` -> ``qwen3-32b``."""
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")


def episode_path(study_dir: Path, model_short: str, dataset_token: str, attempt: str) -> Path:
    return study_dir / f"episode-{model_short}-{dataset_token}-{attempt}.json"


def make_episode(
    *, dataset: str, attempt: str, model: str, response_text: str,
    rows: int | None, method: str, gen_params: dict,
) -> dict:
    """local_harvest.build_episode with the model-short corrected for the ladder."""
    episode = LH.build_episode(
        dataset=dataset, attempt=attempt, model=model,
        response_text=response_text, rows=rows, method=method, gen_params=gen_params,
    )
    episode["modelShort"] = model_short_of(model)
    return episode


def call_ollama(
    prompt: str, *, url: str, model: str, seed: int, temperature: float,
    num_ctx: int, think: bool, num_predict: int | None, timeout: float,
) -> dict:
    """One non-streaming generation; num_predict caps runaway think-mode decodes."""
    options: dict = {"seed": seed, "temperature": temperature, "num_ctx": num_ctx}
    if num_predict is not None:
        options["num_predict"] = num_predict
    payload = {"model": model, "prompt": prompt, "stream": False, "think": think, "options": options}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def harvest(
    *, url: str, model: str, n: int, num_ctx: int, think: bool,
    num_predict: int | None, timeout: float, datasets: dict[str, str],
    overwrite: bool, study_dir: Path,
) -> list[dict]:
    study_dir.mkdir(parents=True, exist_ok=True)
    model_short = model_short_of(model)
    log: list[dict] = []
    for token, dataset in datasets.items():
        dataset_json_text = (DATASETS_DIR / f"{dataset}.json").read_text(encoding="utf-8")
        prompt = LH.build_prompt(dataset, dataset_json_text)
        for i in range(n):
            attempt = f"{i + 1:02d}"
            path = episode_path(study_dir, model_short, token, attempt)
            if path.exists() and not overwrite:
                log.append({"dataset": dataset, "attempt": attempt, "skipped": "exists"})
                continue
            temperature = LH.TEMPERATURE_CYCLE[i % len(LH.TEMPERATURE_CYCLE)]
            seed = i + 1
            t0 = time.monotonic()
            try:
                result = call_ollama(
                    prompt, url=url, model=model, seed=seed, temperature=temperature,
                    num_ctx=num_ctx, think=think, num_predict=num_predict, timeout=timeout,
                )
            except (urllib.error.URLError, TimeoutError) as exc:
                log.append({"dataset": dataset, "attempt": attempt, "error": str(exc)})
                print(f"[{model} {dataset} {attempt}] generation error: {exc}", flush=True)
                continue
            wall = round(time.monotonic() - t0, 2)
            response_text = result.get("response", "")
            prompt_tokens = result.get("prompt_eval_count")
            eval_tokens = result.get("eval_count")
            truncated = bool(prompt_tokens is not None and prompt_tokens >= num_ctx)
            # A think-mode decode that hit the num_predict cap produced no final
            # answer by construction; record it, never score it as a count.
            capped = bool(num_predict is not None and eval_tokens is not None and eval_tokens >= num_predict)
            rows, method = LH.extract_count(response_text)
            if capped and rows is None:
                method = "decode-cap-hit"
            gen_params = {
                "seed": seed, "temperature": temperature, "num_ctx": num_ctx,
                "think": think, "numPredict": num_predict, "decodeCapHit": capped,
                "promptEvalCount": prompt_tokens, "evalCount": eval_tokens,
                "wallClockSec": wall, "truncated": truncated,
            }
            episode = make_episode(
                dataset=dataset, attempt=attempt, model=model,
                response_text=response_text, rows=rows, method=method, gen_params=gen_params,
            )
            path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            log.append({
                "dataset": dataset, "attempt": attempt, "rows": rows, "method": method,
                "truncated": truncated, "promptTokens": prompt_tokens, "wall": wall,
            })
            flag = " TRUNCATED" if truncated else (" CAP-HIT" if capped else "")
            shown = rows if rows is not None else f"PARSE-FAIL({method})"
            print(
                f"[{model} {dataset} {attempt}] rows={shown} promptTok={prompt_tokens} "
                f"evalTok={eval_tokens} {wall}s{flag} -> {path.name}",
                flush=True,
            )
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="ollama model tag (e.g. qwen3:14b, qwen3:32b)")
    parser.add_argument("--n", type=int, default=20, help="attempts per dataset")
    parser.add_argument("--num-ctx", type=int, default=40960)
    parser.add_argument("--num-predict", type=int, default=None, help="decode cap (recommended for --think)")
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--think", dest="think", action="store_true")
    parser.add_argument("--no-think", dest="think", action="store_false")
    parser.add_argument("--only", default=None, help="restrict to one dataset token (f or g)")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--study-dir", default=str(STUDY_DIR))
    parser.add_argument("--url", default=LH.OLLAMA_URL, help="ollama generate endpoint")
    parser.set_defaults(think=False)
    args = parser.parse_args(argv)

    datasets = dict(LH.DATASET_TOKENS)  # f + g; h stays excluded (same condition as the 8B study)
    if args.only:
        if args.only not in datasets:
            parser.error(f"--only must be one of {sorted(datasets)}")
        datasets = {args.only: datasets[args.only]}

    t0 = time.monotonic()
    log = harvest(
        url=args.url, model=args.model, n=args.n, num_ctx=args.num_ctx,
        think=args.think, num_predict=args.num_predict, timeout=args.timeout,
        datasets=datasets, overwrite=args.overwrite, study_dir=Path(args.study_dir),
    )
    total = round(time.monotonic() - t0, 1)
    generated = [r for r in log if "rows" in r]
    parse_fail = [r for r in generated if r.get("rows") is None]
    truncated = [r for r in generated if r.get("truncated")]
    print(
        f"\ngpu harvest [{args.model}]: {len(generated)} generated "
        f"({len(parse_fail)} parse-failures, {len(truncated)} truncated), "
        f"{sum(1 for r in log if r.get('skipped'))} skipped, "
        f"{sum(1 for r in log if 'error' in r)} errors in {total}s -> {args.study_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
