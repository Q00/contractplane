from __future__ import annotations

from pathlib import Path

import pytest

from contractplane.compiler import compile_plan, inspect_pack
from contractplane.errors import CompileError
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PACK = load_domain_pack(ROOT / "examples" / "hello-domain" / "domainpack.yaml")


def test_compile_groups_maximal_topological_waves() -> None:
    plan = compile_plan(PACK, entrypoint_id="hello")
    assert [[stage.id for stage in wave.stages] for wave in plan.waves] == [
        ["normalize"],
        ["draft"],
        ["publish", "archive"],
    ]
    assert [stage.id for stage in plan.stages] == [
        "normalize",
        "draft",
        "publish",
        "archive",
    ]


def test_compile_preserves_binding_permissions_condition_and_contracts() -> None:
    plan = compile_plan(PACK, flow_id="greet")
    publish = plan.stage_map["publish"]
    archive = plan.stage_map["archive"]
    assert publish.binding == {
        "adapter": "http",
        "target": "https://example.invalid/greetings",
        "config": {"method": "POST"},
    }
    assert publish.permissions == (
        "network:example.invalid",
        "external:greeting.write",
    )
    assert publish.evidence_contracts[0]["id"] == "publication-receipt"
    assert archive.when == "inputs.archive == true"
    assert archive.produces == ("archive",)


def test_compile_is_byte_deterministic_and_digest_covers_plan() -> None:
    first = compile_plan(PACK, entrypoint_id="hello")
    second = compile_plan(PACK, entrypoint_id="hello")
    assert first.to_json() == second.to_json()
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_compile_rejects_unknown_or_ambiguous_selector() -> None:
    with pytest.raises(CompileError, match="unknown flow"):
        compile_plan(PACK, flow_id="missing")
    with pytest.raises(CompileError, match="unknown entrypoint"):
        compile_plan(PACK, entrypoint_id="missing")
    with pytest.raises(CompileError, match="either flow or entrypoint"):
        compile_plan(PACK, flow_id="greet", entrypoint_id="hello")


def test_inspect_exposes_topology_and_unused_capabilities() -> None:
    report = inspect_pack(PACK)
    assert report["counts"]["flows"] == 1
    assert report["flows"][0]["waves"] == [
        ["normalize"],
        ["draft"],
        ["publish", "archive"],
    ]
    assert all(item["used"] for item in report["capabilities"])
