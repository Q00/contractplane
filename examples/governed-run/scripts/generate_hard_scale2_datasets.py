#!/usr/bin/env python3
"""Deterministically generate the SHORTCUT-CLOSED hard-count datasets (EXPERIMENTAL).

Methodological fix for the ``hard-count-c/d/e`` scale datasets. Inspection found
that c/d/e admitted O(1)/O(groups) shortcuts that let a model skip enumeration:

* record ids were SEQUENTIAL (``rec-000001 .. rec-001523``), so the last id
  directly reveals the count; and
* group sizes were UNIFORM (13 records per group), so the count is recoverable as
  ``groups x 13 + remainder`` without reading the records.

Recorded responses confirmed models exploited these regularities (structural
multiplication), which fully explains the earlier 9/9 perfect result. See the
experiments ledger row ``e8-scale-shortcut-discovery``.

``hard-count-f/g/h`` keep the SAME counting rule (structure ``nested-groups``: a
record is any ``groups[*].items[*]`` with ``kind == "record"``) at the same scales
(~300 / ~800 / ~1500 records) but close both shortcuts:

* ids are random, shuffled, letter-led base-36 tokens with NO sequential or
  count-revealing structure (no id is a plain integer, no id encodes its position,
  the id order is not sorted); and
* group sizes are drawn irregularly in ``[MIN_GROUP, MAX_GROUP]`` so there is no
  uniform multiplier.

Difficulty density (record-shaped metadata, near-duplicate ids) matches the earlier
datasets. The generator asserts, by construction, that none of the closed shortcuts
survive (see :func:`assert_no_shortcut`). Ground truth is the enumerated record
count and is pinned in ``tests/test_experimental_natural_scale2_study.py``.

Usage (from the repo root):

    .venv/bin/python examples/governed-run/scripts/generate_hard_scale2_datasets.py
    .venv/bin/python examples/governed-run/scripts/generate_hard_scale2_datasets.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets"

# (name, group_count, rng_seed). The exact record count is whatever the seeded
# irregular group sizes sum to -- deliberately NOT a chosen target, so nothing in
# the construction encodes it. The resulting counts land near ~300/~800/~1500 and
# are pinned in the test.
SCALE2_SPECS: tuple[tuple[str, int, int], ...] = (
    ("hard-count-f", 19, 90211),
    ("hard-count-g", 48, 90222),
    ("hard-count-h", 90, 90233),
)

MIN_GROUP = 3
MAX_GROUP = 31
# A record-shaped metadata item appears with this probability per group slot,
# and near-duplicate record ids at this rate -- matching c/d/e trap density.
METADATA_PER_GROUP = (1, 2, 3)
METADATA_WEIGHTS = (30, 45, 25)
NEAR_DUP_RATE = 0.05

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_LEAD = "abcdefghijklmnopqrstuvwxyz"
REC_LABELS = (
    "ingest", "parse", "normalize", "dedupe", "enrich", "score", "rank", "route",
    "emit", "audit", "retry", "flush", "compact", "index",
)


def _token(rng: random.Random, length: int = 9) -> str:
    """A random, letter-led base-36 token (never a plain integer)."""
    return rng.choice(_LEAD) + "".join(rng.choice(_ALPHABET) for _ in range(length - 1))


# The per-record numeric field the aggregate (sum) family totals. It is derived
# deterministically from the id via a stable hash (NOT the structural rng), so
# adding it leaves every id, label, group size, and record count byte-identical to
# the count-only datasets -- only the new `value` key is added. Near-duplicate
# records (same id) therefore carry the same value and are each summed. The sum is
# not recoverable without enumerating every record.
def _value(token: str) -> int:
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()
    return int(digest, 16) % 99 + 1  # 1..99


def build_nested(name: str, group_count: int, seed: int) -> dict:
    """Build a nested-groups dataset with irregular group sizes and random ids."""
    rng = random.Random(seed)
    groups: list[dict] = []
    prev_id: str | None = None
    for gi in range(group_count):
        size = rng.randint(MIN_GROUP, MAX_GROUP)
        items: list[dict] = []
        for _ in range(size):
            if prev_id is not None and rng.random() < NEAR_DUP_RATE:
                rid = prev_id  # near-duplicate id: still a distinct record
            else:
                rid = _token(rng)
            items.append({
                "id": rid,
                "kind": "record",
                "label": rng.choice(REC_LABELS),
                "value": _value(rid),
            })
            prev_id = rid
        meta_here = rng.choices(METADATA_PER_GROUP, weights=METADATA_WEIGHTS, k=1)[0]
        for _ in range(meta_here):
            items.append({
                "id": _token(rng),
                "kind": "metadata",
                "label": "group-annotation (NOT a record)",
            })
        rng.shuffle(items)  # records and metadata interleaved; no positional order
        groups.append({"id": _token(rng, 6), "title": f"segment {gi + 1}", "items": items})
    return {
        "dataset": name,
        "structure": "nested-groups",
        "recordDiscriminator": "item.kind == 'record'",
        "sumField": "value",
        "shortcutClosed": True,
        "groups": groups,
    }


def count_records(data: dict) -> int:
    return sum(
        1
        for group in data["groups"]
        for item in group["items"]
        if item.get("kind") == "record"
    )


def _digit_run(token: str) -> str:
    return "".join(ch for ch in token if ch.isdigit())


def assert_no_shortcut(data: dict) -> None:
    """Fail loudly if any O(1)/O(groups) count-revealing regularity survives.

    These are the two shortcuts that c/d/e admitted: a last/only id that reads as
    the count, and a uniform group size that makes the count a simple multiple.
    """
    count = count_records(data)
    record_ids = [
        item["id"]
        for group in data["groups"]
        for item in group["items"]
        if item.get("kind") == "record"
    ]
    group_sizes = [
        sum(1 for item in group["items"] if item.get("kind") == "record")
        for group in data["groups"]
    ]

    # 1. Group sizes are irregular -> count is not `groups x k (+ remainder)`.
    assert min(group_sizes) != max(group_sizes), "group sizes are uniform"
    assert len(set(group_sizes)) >= 4, "group sizes are too regular"

    # 2. No id is a plain integer, so no id can be read as the count by itself.
    assert all(not rid.isdigit() for rid in record_ids), "an id is a bare integer"

    # 3. The last id's digit run does not equal the count -- the exact c/d/e flaw,
    #    where the final `rec-00NNNN` spelled out the total. (An interior id whose
    #    scattered digits coincidentally equal the count is not a usable shortcut:
    #    a reader cannot identify it as special without already having counted.)
    assert _digit_run(record_ids[-1]) != str(count), "the last id's digits equal the count"

    # 4. Ids are not sequential/sorted -> position cannot be recovered from an id.
    assert record_ids != sorted(record_ids), "record ids are in sorted order"

    # 5. Group ids carry no integer ordering that reveals the group count.
    group_ids = [group["id"] for group in data["groups"]]
    assert all(not gid.isdigit() for gid in group_ids), "a group id is a bare integer"
    assert group_ids != sorted(group_ids), "group ids are in sorted order"


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the shortcut-closed hard-count datasets.")
    parser.add_argument("--check", action="store_true", help="verify committed files without rewriting")
    args = parser.parse_args(argv)

    drift = False
    for name, group_count, seed in SCALE2_SPECS:
        data = build_nested(name, group_count, seed)
        assert_no_shortcut(data)
        count = count_records(data)
        text = render(data)
        path = DATASETS_DIR / f"{name}.json"
        detail = f"{count} records, {len(data['groups'])} groups (sizes vary)"
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
