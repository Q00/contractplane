from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .errors import DomainPackValidationError, ValidationIssue
from .models import (
    Capability,
    CapabilityBinding,
    CapabilityKind,
    DomainPack,
    EntryPoint,
    Evidence,
    EvidenceKind,
    Fanout,
    FanoutMode,
    Flow,
    HumanApproval,
    Metadata,
    Policy,
    Role,
    SideEffect,
    Stage,
)
from .schema import domain_pack_schema

_WHEN_FORBIDDEN = re.compile(r"[;`\x00\r\n]|\$\(")


def _path(parts: Iterable[Any]) -> str:
    rendered = "$"
    for part in parts:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}"
    return rendered


def _structural_issues(raw: Any) -> list[ValidationIssue]:
    validator = Draft202012Validator(domain_pack_schema())
    errors = sorted(validator.iter_errors(raw), key=lambda error: list(error.absolute_path))
    return [ValidationIssue(_path(error.absolute_path), error.message) for error in errors]


def _parse(raw: dict[str, Any]) -> DomainPack:
    metadata = raw["metadata"]
    return DomainPack(
        api_version=raw["apiVersion"],
        kind=raw["kind"],
        metadata=Metadata(
            name=metadata["name"],
            version=metadata["version"],
            description=metadata["description"],
        ),
        default_policy=raw["defaultPolicy"],
        capabilities=tuple(
            Capability(
                id=item["id"],
                kind=CapabilityKind(item["kind"]),
                description=item["description"],
                side_effects=SideEffect(item["sideEffects"]),
                input_schema=item["inputSchema"],
                output_schema=item["outputSchema"],
                permissions=tuple(item["permissions"]),
                binding=(
                    CapabilityBinding(
                        adapter=item["binding"]["adapter"],
                        target=item["binding"]["target"],
                        config=item["binding"].get("config"),
                    )
                    if item.get("binding") is not None
                    else None
                ),
            )
            for item in raw["capabilities"]
        ),
        roles=tuple(
            Role(
                id=item["id"],
                description=item["description"],
                capabilities=tuple(item["capabilities"]),
                instructions=item["instructions"],
            )
            for item in raw["roles"]
        ),
        evidence=tuple(
            Evidence(
                id=item["id"],
                kind=EvidenceKind(item["kind"]),
                description=item["description"],
                schema=item.get("schema"),
            )
            for item in raw["evidence"]
        ),
        policies=tuple(
            Policy(
                id=item["id"],
                description=item["description"],
                evidence_required=item["evidenceRequired"],
                human_approval=HumanApproval(item["humanApproval"]),
                max_attempts=item["maxAttempts"],
            )
            for item in raw["policies"]
        ),
        flows=tuple(
            Flow(
                id=flow["id"],
                description=flow["description"],
                input_schema=flow["inputSchema"],
                stages=tuple(
                    Stage(
                        id=stage["id"],
                        description=stage["description"],
                        capability=stage["capability"],
                        role=stage.get("role"),
                        needs=tuple(stage["needs"]),
                        fanout=Fanout(
                            mode=FanoutMode(stage["fanout"]["mode"]),
                            over=stage["fanout"].get("over"),
                        ),
                        requires_evidence=tuple(stage["requiresEvidence"]),
                        policy=stage.get("policy"),
                        produces=tuple(stage["produces"]),
                        when=stage.get("when"),
                    )
                    for stage in flow["stages"]
                ),
            )
            for flow in raw["flows"]
        ),
        entrypoints=tuple(
            EntryPoint(
                id=item["id"],
                description=item["description"],
                flow=item["flow"],
                keywords=tuple(item["keywords"]),
                examples=tuple(item["examples"]),
            )
            for item in raw["entrypoints"]
        ),
    )


def _duplicate_issues(items: Iterable[Any], collection_path: str) -> list[ValidationIssue]:
    seen: dict[str, int] = {}
    issues: list[ValidationIssue] = []
    for index, item in enumerate(items):
        if item.id in seen:
            issues.append(
                ValidationIssue(
                    f"{collection_path}[{index}].id",
                    f"duplicate id {item.id!r}; first declared at index {seen[item.id]}",
                )
            )
        else:
            seen[item.id] = index
    return issues


def _schema_issue(schema: dict[str, Any], path: str) -> ValidationIssue | None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return ValidationIssue(path, f"invalid embedded JSON Schema: {exc.message}")
    return None


def _cycle_nodes(flow: Flow) -> list[str]:
    stage_ids = [stage.id for stage in flow.stages]
    stage_set = set(stage_ids)
    indegree = {stage_id: 0 for stage_id in stage_ids}
    dependents: dict[str, list[str]] = {stage_id: [] for stage_id in stage_ids}
    for stage in flow.stages:
        for need in stage.needs:
            if need not in stage_set:
                continue
            indegree[stage.id] += 1
            dependents[need].append(stage.id)
    ready = [stage_id for stage_id in stage_ids if indegree[stage_id] == 0]
    visited: list[str] = []
    while ready:
        current = ready.pop(0)
        visited.append(current)
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    return [stage_id for stage_id in stage_ids if stage_id not in visited]


def semantic_issues(pack: DomainPack) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_duplicate_issues(pack.capabilities, "$.capabilities"))
    issues.extend(_duplicate_issues(pack.roles, "$.roles"))
    issues.extend(_duplicate_issues(pack.evidence, "$.evidence"))
    issues.extend(_duplicate_issues(pack.policies, "$.policies"))
    issues.extend(_duplicate_issues(pack.flows, "$.flows"))
    issues.extend(_duplicate_issues(pack.entrypoints, "$.entrypoints"))

    capability_ids = {item.id for item in pack.capabilities}
    role_ids = {item.id for item in pack.roles}
    evidence_ids = {item.id for item in pack.evidence}
    policy_ids = {item.id for item in pack.policies}
    flow_ids = {item.id for item in pack.flows}

    if pack.default_policy not in policy_ids:
        issues.append(
            ValidationIssue(
                "$.defaultPolicy", f"references unknown policy {pack.default_policy!r}"
            )
        )

    for index, capability in enumerate(pack.capabilities):
        for field, schema in (
            ("inputSchema", capability.input_schema),
            ("outputSchema", capability.output_schema),
        ):
            issue = _schema_issue(schema, f"$.capabilities[{index}].{field}")
            if issue:
                issues.append(issue)

    for index, role in enumerate(pack.roles):
        for cap_index, capability_id in enumerate(role.capabilities):
            if capability_id not in capability_ids:
                issues.append(
                    ValidationIssue(
                        f"$.roles[{index}].capabilities[{cap_index}]",
                        f"references unknown capability {capability_id!r}",
                    )
                )

    for index, evidence in enumerate(pack.evidence):
        if evidence.kind is EvidenceKind.JSON_SCHEMA and evidence.schema is None:
            issues.append(
                ValidationIssue(
                    f"$.evidence[{index}].schema",
                    "is required when evidence kind is 'json-schema'",
                )
            )
        if evidence.schema is not None:
            issue = _schema_issue(evidence.schema, f"$.evidence[{index}].schema")
            if issue:
                issues.append(issue)

    for flow_index, flow in enumerate(pack.flows):
        issue = _schema_issue(flow.input_schema, f"$.flows[{flow_index}].inputSchema")
        if issue:
            issues.append(issue)
        issues.extend(_duplicate_issues(flow.stages, f"$.flows[{flow_index}].stages"))
        stage_ids = {stage.id for stage in flow.stages}
        for stage_index, stage in enumerate(flow.stages):
            base = f"$.flows[{flow_index}].stages[{stage_index}]"
            capability = pack.capability_map.get(stage.capability)
            role = pack.role_map.get(stage.role) if stage.role else None
            if capability is None:
                issues.append(
                    ValidationIssue(
                        f"{base}.capability",
                        f"references unknown capability {stage.capability!r}",
                    )
                )
            if stage.role and stage.role not in role_ids:
                issues.append(
                    ValidationIssue(f"{base}.role", f"references unknown role {stage.role!r}")
                )
            if capability is not None and capability.kind is CapabilityKind.AGENT and not stage.role:
                issues.append(
                    ValidationIssue(f"{base}.role", "is required for an agent capability")
                )
            if capability is not None and role is not None and stage.capability not in role.capabilities:
                issues.append(
                    ValidationIssue(
                        f"{base}.role",
                        f"role {role.id!r} does not declare capability {stage.capability!r}",
                    )
                )
            for need_index, need in enumerate(stage.needs):
                if need not in stage_ids:
                    issues.append(
                        ValidationIssue(
                            f"{base}.needs[{need_index}]",
                            f"references unknown stage {need!r} in flow {flow.id!r}",
                        )
                    )
                elif need == stage.id:
                    issues.append(
                        ValidationIssue(f"{base}.needs[{need_index}]", "stage cannot depend on itself")
                    )
            for evidence_index, evidence_id in enumerate(stage.requires_evidence):
                if evidence_id not in evidence_ids:
                    issues.append(
                        ValidationIssue(
                            f"{base}.requiresEvidence[{evidence_index}]",
                            f"references unknown evidence {evidence_id!r}",
                        )
                    )
            policy_id = stage.policy or pack.default_policy
            policy = pack.policy_map.get(policy_id)
            if stage.policy and stage.policy not in policy_ids:
                issues.append(
                    ValidationIssue(
                        f"{base}.policy", f"references unknown policy {stage.policy!r}"
                    )
                )
            if policy is not None and policy.evidence_required and not stage.requires_evidence:
                issues.append(
                    ValidationIssue(
                        f"{base}.requiresEvidence",
                        f"must not be empty because policy {policy.id!r} requires evidence",
                    )
                )
            if stage.fanout.mode is FanoutMode.EACH and not stage.fanout.over:
                issues.append(
                    ValidationIssue(f"{base}.fanout.over", "is required when fanout mode is 'each'")
                )
            if stage.fanout.mode is FanoutMode.SINGLETON and stage.fanout.over:
                issues.append(
                    ValidationIssue(
                        f"{base}.fanout.over", "must be omitted when fanout mode is 'singleton'"
                    )
                )
            if stage.when is not None:
                if len(stage.when) > 512:
                    issues.append(
                        ValidationIssue(f"{base}.when", "condition exceeds the 512 character limit")
                    )
                if _WHEN_FORBIDDEN.search(stage.when):
                    issues.append(
                        ValidationIssue(
                            f"{base}.when",
                            "must be a declarative condition expression, not shell syntax",
                        )
                    )
        cycle = _cycle_nodes(flow)
        if cycle:
            issues.append(
                ValidationIssue(
                    f"$.flows[{flow_index}].stages",
                    f"dependency graph contains a cycle involving: {', '.join(cycle)}",
                )
            )

    for index, entrypoint in enumerate(pack.entrypoints):
        if entrypoint.flow not in flow_ids:
            issues.append(
                ValidationIssue(
                    f"$.entrypoints[{index}].flow",
                    f"references unknown flow {entrypoint.flow!r}",
                )
            )
    return sorted(issues)


def parse_domain_pack(raw: Any) -> DomainPack:
    issues = _structural_issues(raw)
    if issues:
        raise DomainPackValidationError(issues)
    pack = _parse(raw)
    issues = semantic_issues(pack)
    if issues:
        raise DomainPackValidationError(issues)
    return pack


def load_domain_pack(path: str | Path) -> DomainPack:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise DomainPackValidationError(
            [ValidationIssue("$", f"DomainPack file does not exist: {source}")]
        )
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DomainPackValidationError([ValidationIssue("$", f"invalid YAML: {exc}")]) from exc
    return parse_domain_pack(raw)
