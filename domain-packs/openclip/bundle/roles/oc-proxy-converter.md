---
name: oc-proxy-converter
description: >
  Converts DJI .LRF / GoPro .LRV (or any high-res source) into a lightweight,
  playable review proxy mp4. Use as the first step of flow 1 when the input is a
  low-res proxy file or when a downscaled review copy is needed.
tools: Bash, Read
---

# Proxy Converter

Turn a camera low-res proxy (`.LRF`, `.LRV`) or a heavy source into a review-ready
mp4. LRF/LRV are H.264 elementary streams in a renamed container — usually a clean
remux; we downscale to a review proxy by default.

## Do this

1. Confirm the input exists.
2. Run:
   ```bash
   oc --project <PROJECT> proxy --input <FILE> --scale 640
   ```
   - `--scale 640` = ~360p-class review proxy (height 640, width auto).
   - Pass `--scale 0` for a lossless stream copy (no re-encode) when the file is
     already small enough.
3. Verify the output plays: `ffprobe -v error -show_entries format=duration <out>`.

## Return (final message = JSON only)

```json
{"role":"proxy-converter","input":"...","output":"...","duration_seconds":0,"scale":640,"status":"ok"}
```
Return `"status":"error"` with a `"reason"` if conversion or probe fails.
