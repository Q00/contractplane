#!/usr/bin/env python3
"""Deterministically generate the scaled hard-count datasets (EXPERIMENTAL).

These datasets extend the spontaneous-error ("natural") study with a SCALE
dimension. They use the SAME documented counting rule as ``hard-count-a``
(structure ``nested-groups``): a RECORD is any element of ``groups[*].items[*]``
whose ``kind`` equals ``"record"``; ``kind == "metadata"`` items are not records;
records sharing an ``id`` (near-duplicates) are each counted. Only the *scale*
grows across c/d/e — the legitimate difficulty features (nested groups,
near-duplicate ids, record-shaped metadata sprinkled throughout) are held at a
similar density, so scale is the single variable, not new trickery.

Ground truth is therefore mechanical: the number of record items equals the
generator's ``records`` target exactly. Re-running this script reproduces the
committed files byte-for-byte. The true counts are pinned in
``tests/test_experimental_natural_scale_study.py``.

Usage (from the repo root):

    .venv/bin/python examples/governed-run/scripts/generate_hard_scale_datasets.py

Add ``--check`` to verify the committed files match a fresh generation without
rewriting them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets"

# (name, exact record count). Deliberately non-round so a genuine tool-less
# reader must actually count rather than guess a tidy target.
SCALE_SPECS: tuple[tuple[str, int], ...] = (
    ("hard-count-c", 307),
    ("hard-count-d", 794),
    ("hard-count-e", 1523),
)

# Difficulty knobs held constant across scales (density, not scale, of trickery).
RECORDS_PER_GROUP = 13
NEAR_DUP_EVERY = 18   # every Nth record reuses the previous record's id
METADATA_EVERY_GROUP = 1  # one record-shaped metadata item per group ...
METADATA_DOUBLE_EVERY = 4  # ... and a second one in every 4th group

REC_LABELS = (
    "ingest", "parse", "normalize", "dedupe", "enrich", "score", "rank", "route",
    "emit", "audit", "retry", "flush", "compact", "index",
)


def build_nested(name: str, records: int) -> dict:
    """Build a nested-groups dataset with exactly ``records`` record items."""
    groups: list[dict] = []
    rec_counter = 0
    prev_id: str | None = None
    remaining = records
    group_index = 0
    while remaining > 0:
        group_index += 1
        take = min(RECORDS_PER_GROUP, remaining)
        items: list[dict] = []
        for _ in range(take):
            rec_counter += 1
            if rec_counter % NEAR_DUP_EVERY == 0 and prev_id is not None:
                rid = prev_id  # near-duplicate id: still a distinct record
            else:
                rid = f"rec-{rec_counter:06d}"
            items.append({
                "id": rid,
                "kind": "record",
                "label": REC_LABELS[(rec_counter - 1) % len(REC_LABELS)],
            })
            prev_id = rid
        meta_here = METADATA_EVERY_GROUP + (1 if group_index % METADATA_DOUBLE_EVERY == 0 else 0)
        for m in range(meta_here):
            items.append({
                "id": f"meta-{group_index:04d}-{m + 1}",
                "kind": "metadata",
                "label": "group-annotation (NOT a record)",
            })
        groups.append({"id": f"grp-{group_index:04d}", "title": f"segment {group_index}", "items": items})
        remaining -= take
    return {
        "dataset": name,
        "structure": "nested-groups",
        "recordDiscriminator": "item.kind == 'record'",
        "groups": groups,
    }


def count_records(data: dict) -> int:
    return sum(
        1
        for group in data["groups"]
        for item in group["items"]
        if item.get("kind") == "record"
    )


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the scaled hard-count datasets.")
    parser.add_argument("--check", action="store_true", help="verify committed files without rewriting")
    args = parser.parse_args(argv)

    drift = False
    for name, target in SCALE_SPECS:
        data = build_nested(name, target)
        actual = count_records(data)
        assert actual == target, f"{name}: generated {actual} records, expected {target}"
        text = render(data)
        path = DATASETS_DIR / f"{name}.json"
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            status = "ok" if current == text else "DRIFT"
            drift = drift or status == "DRIFT"
            print(f"{name}: {target} records, {len(data['groups'])} groups -> {status}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"{name}: {target} records, {len(data['groups'])} groups -> {path}")

    if args.check and drift:
        print("committed datasets differ from a fresh generation")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
