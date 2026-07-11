from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from contractplane.compiler import compile_plan
from contractplane.errors import DomainPackValidationError
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "domain-packs" / "incident-response" / "incident-response.yaml"
ROLES = ROOT / "domain-packs" / "incident-response" / "roles"
LOCK = ROOT / "domain-packs" / "incident-response" / "pack.lock.json"
GOLDEN = ROOT / "conformance" / "incident-response" / "respond.plan.json"
INVALID = ROOT / "conformance" / "incident-response" / "invalid"


def test_incident_response_pack_validates_and_compiles_all_flows() -> None:
    pack = load_domain_pack(PACK)
    assert pack.metadata.name == "incident-response"
    assert {flow.id for flow in pack.flows} == {"respond", "contain"}
    for flow in pack.flows:
        plan = compile_plan(pack, flow_id=flow.id)
        assert plan.flow == flow.id
        assert plan.waves


def test_incident_response_respond_plan_matches_golden_and_lock() -> None:
    pack = load_domain_pack(PACK)
    plan = compile_plan(pack, entrypoint_id="respond")
    assert json.loads(plan.to_json()) == json.loads(GOLDEN.read_text(encoding="utf-8"))

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["schema"] == "contractplane-domain-native-lock-v1"
    assert lock["origin"] == "native"
    assert lock["packSha256"] == hashlib.sha256(PACK.read_bytes()).hexdigest()
    compiled = lock["compiledPlans"][0]
    assert compiled["sha256"] == hashlib.sha256(GOLDEN.read_bytes()).hexdigest()
    assert compiled["planDigest"] == plan.digest


def test_incident_response_native_lock_covers_the_role_contracts() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert len(lock["roleContracts"]) == 5
    for role in lock["roleContracts"]:
        path = ROOT / "domain-packs" / "incident-response" / role["path"]
        assert path.is_file()
        assert role["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    # Every agent role bound in the pack ships a locked contract file.
    pack = load_domain_pack(PACK)
    locked_roles = {role["role"] for role in lock["roleContracts"]}
    assert {role.id for role in pack.roles} == locked_roles


def test_incident_response_plan_exercises_integration_external_side_effects() -> None:
    plan = compile_plan(load_domain_pack(PACK), entrypoint_id="respond")
    stages = plan.stage_map

    # The scatter/gather investigation shape: fan out over live triage scope.
    assert stages["investigate"].fanout == {"mode": "each", "over": "affected-systems"}
    assert stages["correlate"].fanout == {"mode": "singleton"}

    # External-side-effect containment is an integration capability with no agent role.
    contain = stages["contain"]
    assert contain.capability_kind == "integration"
    assert contain.side_effects == "external"
    assert contain.role is None
    assert contain.binding == {
        "adapter": "ir-integration",
        "target": "edr-quarantine",
        "config": {"system": "crowdstrike-falcon", "action": "network-contain"},
    }
    assert contain.fanout == {"mode": "each", "over": "root-cause.compromised-systems"}

    # It is blocked behind mandatory human approval plus a third-party receipt.
    assert contain.policy["id"] == "command-authorized"
    assert contain.policy["humanApproval"] == "always"
    assert contain.requires_evidence == ("approval-receipt", "containment-receipt")
    receipts = {contract["id"]: contract["kind"] for contract in contain.evidence_contracts}
    assert receipts == {
        "approval-receipt": "external-receipt",
        "containment-receipt": "external-receipt",
    }

    # The notify integration is gated the same way; the postmortem is evidence-required.
    assert stages["notify"].capability_kind == "integration"
    assert stages["notify"].policy["humanApproval"] == "always"
    assert stages["postmortem"].requires_evidence == ("postmortem-complete",)


def test_incident_response_invalid_fixtures_are_rejected() -> None:
    fixtures = sorted(INVALID.glob("*.yaml"))
    assert fixtures
    for path in fixtures:
        with pytest.raises(DomainPackValidationError):
            load_domain_pack(path)
