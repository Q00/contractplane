from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from contractplane.errors import DomainPackValidationError
from contractplane.loader import load_domain_pack, parse_domain_pack

ROOT = Path(__file__).resolve().parents[1]
HELLO = ROOT / "examples" / "hello-domain" / "domainpack.yaml"


def _raw() -> dict:
    return yaml.safe_load(HELLO.read_text(encoding="utf-8"))


def test_load_valid_pack_roundtrips_canonical_contract() -> None:
    pack = load_domain_pack(HELLO)
    assert pack.metadata.name == "hello-domain"
    assert pack.to_dict() == _raw()
    publish = pack.flow_map["greet"].stages[2]
    assert publish.policy == "external-change"
    assert pack.capability_map["publish-greeting"].binding is not None
    assert pack.capability_map["publish-greeting"].permissions == (
        "network:example.invalid",
        "external:greeting.write",
    )


def test_structural_schema_rejects_unknown_fields() -> None:
    raw = _raw()
    raw["capabilities"][0]["shell"] = "rm -rf /"
    with pytest.raises(DomainPackValidationError) as exc:
        parse_domain_pack(raw)
    assert any(issue.path == "$.capabilities[0]" for issue in exc.value.issues)
    assert "Additional properties" in str(exc.value)


def test_agent_capability_requires_authorized_role() -> None:
    raw = _raw()
    draft = raw["flows"][0]["stages"][1]
    draft.pop("role")
    with pytest.raises(DomainPackValidationError) as exc:
        parse_domain_pack(raw)
    assert any(issue.path.endswith(".role") for issue in exc.value.issues)
    assert "required for an agent capability" in str(exc.value)


def test_role_must_declare_stage_capability() -> None:
    raw = _raw()
    raw["roles"][0]["capabilities"] = ["normalize-name"]
    with pytest.raises(DomainPackValidationError) as exc:
        parse_domain_pack(raw)
    assert "does not declare capability" in str(exc.value)


def test_evidence_required_policy_rejects_ungated_stage() -> None:
    raw = _raw()
    raw["flows"][0]["stages"][0]["requiresEvidence"] = []
    with pytest.raises(DomainPackValidationError) as exc:
        parse_domain_pack(raw)
    assert "must not be empty" in str(exc.value)


def test_invalid_embedded_json_schema_is_rejected() -> None:
    raw = _raw()
    raw["capabilities"][0]["inputSchema"] = {"type": "definitely-not-a-json-type"}
    with pytest.raises(DomainPackValidationError) as exc:
        parse_domain_pack(raw)
    assert "invalid embedded JSON Schema" in str(exc.value)


def test_fanout_each_requires_selector_and_singleton_forbids_it() -> None:
    missing = _raw()
    missing["flows"][0]["stages"][0]["fanout"].pop("over")
    with pytest.raises(DomainPackValidationError, match="fanout.over"):
        parse_domain_pack(missing)

    extra = _raw()
    extra["flows"][0]["stages"][2]["fanout"]["over"] = "$.greetings"
    with pytest.raises(DomainPackValidationError, match="must be omitted"):
        parse_domain_pack(extra)


def test_when_is_declarative_data_not_shell_syntax() -> None:
    raw = copy.deepcopy(_raw())
    raw["flows"][0]["stages"][3]["when"] = "$(touch /tmp/owned)"
    with pytest.raises(DomainPackValidationError, match="not shell syntax"):
        parse_domain_pack(raw)


def test_cycle_is_reported_as_semantic_error() -> None:
    with pytest.raises(DomainPackValidationError) as exc:
        load_domain_pack(ROOT / "conformance" / "invalid" / "cycle.yaml")
    assert "dependency graph contains a cycle" in str(exc.value)
