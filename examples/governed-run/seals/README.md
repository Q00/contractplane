# Commit-reveal seals for harvest ground truths

Blinding in the natural-error studies is procedural (recorders are never told the
truths). A seal makes it auditable: BEFORE any recording, the orchestrator commits
the sha256 of `{"salt": <random hex>, "truths": {...}}` (canonical JSON, sorted
keys, no whitespace) to this directory; the preimage file stays local (gitignored
via `PREIMAGE-*.local.json`) until every recording in scope is complete, then it is
published (committed) as the reveal.

- Create: `.venv/bin/python examples/governed-run/tools/make_seal.py --tag <tag>`
- Verify: `.venv/bin/python -m contractplane.experimental.sealing seals/seal-<tag>.json seals/PREIMAGE-seal-<tag>.local.json`

A verified seal proves the datasets/truths were fixed before the models ran —
they were not tuned after seeing model outputs. The salt prevents brute-forcing
the (small) truth space from the committed hash. Module:
`src/contractplane/experimental/sealing.py`.

Reveal log:
- 2026-07-12: seal-2026-07-12-trackAB REVEALED after both tracks completed (Track B GPU ladder + think arm, e18/e21; Track A OpenAI family, e22; ladder judge corpus, e19). Verification: matches=true.
