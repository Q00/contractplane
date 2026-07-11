from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contractplane.compiler import compile_plan
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "domain-packs" / "openclip" / "openclip.yaml"
BUNDLE = ROOT / "domain-packs" / "openclip" / "bundle"
BUNDLE_LOCK = BUNDLE / "lock.json"
GOLDEN = ROOT / "conformance" / "openclip" / "flow2-shorts.plan.json"
LOCK = ROOT / "domain-packs" / "openclip" / "SOURCE.lock.json"


def test_openclip_pack_validates_and_compiles_all_flows() -> None:
    pack = load_domain_pack(PACK)
    assert pack.metadata.name == "openclip"
    assert {flow.id for flow in pack.flows} == {"cut-edit", "shorts", "assemble", "thumbnails"}
    for flow in pack.flows:
        plan = compile_plan(pack, flow_id=flow.id)
        assert plan.flow == flow.id
        assert plan.waves


def test_openclip_shorts_plan_matches_golden_and_lock() -> None:
    pack = load_domain_pack(PACK)
    plan = compile_plan(pack, entrypoint_id="shorts")
    assert json.loads(plan.to_json()) == json.loads(GOLDEN.read_text(encoding="utf-8"))

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["packSha256"] == hashlib.sha256(PACK.read_bytes()).hexdigest()
    assert lock["compiledFixture"]["sha256"] == hashlib.sha256(GOLDEN.read_bytes()).hexdigest()
    assert lock["compiledFixture"]["planDigest"] == plan.digest


def test_openclip_source_lock_covers_the_self_contained_bundle() -> None:
    source_lock = json.loads(LOCK.read_text(encoding="utf-8"))
    bundle_lock = json.loads(BUNDLE_LOCK.read_text(encoding="utf-8"))

    assert source_lock["schema"] == "contractplane-domain-source-lock-v2"
    assert source_lock["source"]["repository"] == "https://github.com/Q00/openclip"
    assert source_lock["source"]["version"] == "0.2.4"
    assert source_lock["source"]["release"] == "v0.2.4"
    assert len(source_lock["source"]["baseCommit"]) == 40
    assert source_lock["bundleLock"]["sha256"] == hashlib.sha256(
        BUNDLE_LOCK.read_bytes()
    ).hexdigest()

    manifest = BUNDLE / "openclip.domain.yaml"
    assert manifest.read_bytes() == PACK.read_bytes()
    assert bundle_lock["packSha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()

    assert len(bundle_lock["roleContracts"]) == 13
    assert len(source_lock["roleContracts"]) == 13
    for role in bundle_lock["roleContracts"]:
        path = BUNDLE / role["path"]
        assert path.is_file()
        assert role["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()

    for compiled in bundle_lock["compiledPlans"]:
        path = BUNDLE / compiled["path"]
        assert path.is_file()
        assert compiled["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["planDigest"] == compiled["planDigest"]


def test_openclip_short_plan_carries_bindings_permissions_and_evidence() -> None:
    plan = compile_plan(load_domain_pack(PACK), entrypoint_id="shorts")
    stages = plan.stage_map
    assert stages["ingest"].binding == {"adapter": "openclip-cli", "target": "ingest"}
    assert "filesystem.read" in stages["ingest"].permissions
    assert stages["transcribe"].fanout["mode"] == "each"
    assert stages["transcribe"].fanout["over"] == "chunk-manifest.chunks"
    assert stages["hooks"].policy["humanApproval"] == "always"
    assert stages["verify"].requires_evidence == ("mechanical-verdict", "semantic-verdict")
