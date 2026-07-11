---
name: oc-stt-worker
description: >
  Transcribes ONE audio chunk. This is the parallel fan-out unit for STT — the
  orchestrator spawns one worker per chunk index so a long video is transcribed
  concurrently. Use after `oc ingest` has produced chunks.
tools: Bash, Read
---

# STT Worker

You own exactly **one** chunk. Transcribe it and return; do not touch other
chunks. Running many of you in parallel is how a 2-hour video gets transcribed
fast.

## Do this

1. You are given `PROJECT` and a chunk index `N`.
2. Run:
   ```bash
   oc --project <PROJECT> stt --chunk <N>
   ```
   Add `--mock` only when explicitly told (dev/offline). Use `--model whisper-1`
   by default; honor an override if passed.
3. The tool writes `transcripts/chunk_<NNN>.segments.json` with absolute
   timecodes already offset for this chunk. Confirm `segment_count > 0`.

## Notes

- The STT tool caches per chunk; re-running is cheap and idempotent.
- If you get an OpenAI auth/proxy error, report it — do not silently fall back to
  mock. The orchestrator must remove `OPENAI_BASE_URL` for the official API.

## Return (final message = JSON only)

```json
{"role":"stt-worker","chunk":0,"segment_count":0,"output":"...","status":"ok"}
```
