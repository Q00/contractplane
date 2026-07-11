#!/usr/bin/env python3
"""Deterministically generate INDEPENDENT shortcut-closed datasets per scale band.

Methodological fix for a confound reviewers raised about the scale study: each
error-prone scale was a *single* dataset regenerated larger, so "scale" and
"dataset identity" were inseparable. This script adds two more **independent**
datasets at each of the two error-prone bands, drawn with **different seeds** (so
different group-size draws, different random ids, different trap placements) but
the **same rule, family, and scale band**:

* band g (~750-800 records): ``hard-count-g2``, ``hard-count-g3``
  (alongside the existing ``hard-count-g`` = 754);
* band h (~1500-1600 records): ``hard-count-h2``, ``hard-count-h3``
  (alongside the existing ``hard-count-h`` = 1551).

Each band now contains **three independent datasets**, so a scale effect measured
across a band can no longer be an artifact of one dataset's identity.

The datasets are built by the exact same family as ``hard-count-f/g/h`` — this
script imports :func:`build_nested`, :func:`assert_no_shortcut`,
:func:`count_records`, and :func:`render` from
``generate_hard_scale2_datasets.py`` and only supplies new (group_count, seed)
specs. Ground truth is the enumerated record count and is pinned in
``tests/test_experimental_natural_scale3_study.py``.

Usage (from the repo root):

    .venv/bin/python examples/governed-run/scripts/generate_hard_scale3_datasets.py
    .venv/bin/python examples/governed-run/scripts/generate_hard_scale3_datasets.py --check
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
DATASETS_DIR = _SCRIPTS.parent / "datasets"

# Reuse the scale2 generator family verbatim (same rule, same value field, same
# assert_no_shortcut) so only the seed differs.
_spec = importlib.util.spec_from_file_location(
    "_scale2gen", _SCRIPTS / "generate_hard_scale2_datasets.py"
)
_scale2 = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_scale2)
build_nested = _scale2.build_nested
assert_no_shortcut = _scale2.assert_no_shortcut
count_records = _scale2.count_records
render = _scale2.render

# (name, group_count, seed) — seeds distinct from the scale2 family (90211/90222/90233).
# group_count chosen so the seeded irregular sizes sum into the band; the exact
# count is whatever the draws produce and is pinned in the test.
SCALE3_SPECS: tuple[tuple[str, int, int], ...] = (
    ("hard-count-g2", 47, 70576),
    ("hard-count-g3", 46, 70656),
    ("hard-count-h2", 90, 70767),
    ("hard-count-h3", 92, 71142),
)

BANDS = {
    "g": (740, 810),   # acceptable record-count band for g2/g3
    "h": (1480, 1620),  # ... and for h2/h3
}


def _band(name: str) -> str:
    return "g" if "-g" in name else "h"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the independent per-band hard datasets.")
    parser.add_argument("--check", action="store_true", help="verify committed files without rewriting")
    args = parser.parse_args(argv)

    drift = False
    for name, group_count, seed in SCALE3_SPECS:
        data = build_nested(name, group_count, seed)
        assert_no_shortcut(data)
        count = count_records(data)
        lo, hi = BANDS[_band(name)]
        assert lo <= count <= hi, f"{name}: {count} records outside band [{lo}, {hi}]"
        text = render(data)
        path = DATASETS_DIR / f"{name}.json"
        detail = f"{count} records, {len(data['groups'])} groups (sizes vary), band {_band(name)}"
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            status = "ok" if current == text else "DRIFT"
            drift = drift or status == "DRIFT"
            print(f"{name}: {detail} -> {status}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"{name}: {detail} -> {path}")

    if args.check and drift:
        print("committed datasets differ from a fresh generation")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
