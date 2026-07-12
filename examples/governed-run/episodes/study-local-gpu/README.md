# study-local-gpu — Track B: GPU model-ladder natural-error harvest

Fixtures: `episode-<model-short>-<f|g>-<NN>.json`, recorded by
`tools/gpu_harvest.py` (a thin wrapper over the executed `tools/local_harvest.py`
— identical task/prompt/extraction by construction; drift-guarded by tests).

Conditions (each a recorded variable in `generationParams`, never a silent change):
- **model**: the ladder — qwen3:14b, qwen3:32b (optionally a second vendor).
- **think**: matched think arm (`--think --num-predict 16384`); a decode that hits
  the cap is recorded with `decodeCapHit: true` and scores as parse-failure-as-data,
  never as a count.
- **num_ctx**: 40960 (as the 8B study); datasets f + g only, h stays excluded so
  the condition matches the 8B study exactly.

Honesty protocol identical to study-local (tool-less, blind, verbatim claims,
parse-failure-as-data, `real-recorded` only citable). Ground truths were
commit-reveal sealed BEFORE any recording here:
`seals/seal-2026-07-12-trackAB.json` (sha256 8026bf0c…).

Replay/aggregate:

    .venv/bin/python examples/governed-run/family_study_runner.py \
        --dir examples/governed-run/episodes/study-local-gpu \
        --family local-gpu --out artifacts/local_gpu_family_study.json
