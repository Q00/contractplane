from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .errors import CompileError
from .models import DomainPack, Flow, Stage

PLAN_API_VERSION = "contractplane.dev/plan/v1alpha1"
PLAN_KIND = "ExecutionPlan"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


@dataclass(frozen=True)
class CompiledStage:
    id: str
    description: str
    capability: str
    capability_description: str
    capability_kind: str
    side_effects: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: tuple[str, ...]
    binding: dict[str, Any] | None
    role: str | None
    role_contract: dict[str, Any] | None
    needs: tuple[str, ...]
    fanout: dict[str, Any]
    requires_evidence: tuple[str, ...]
    evidence_contracts: tuple[dict[str, Any], ...]
    policy: dict[str, Any]
    produces: tuple[str, ...]
    when: str | None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "capability": self.capability,
            "capabilityDescription": self.capability_description,
            "capabilityKind": self.capability_kind,
            "sideEffects": self.side_effects,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "permissions": list(self.permissions),
            "needs": list(self.needs),
            "fanout": self.fanout,
            "requiresEvidence": list(self.requires_evidence),
            "evidenceContracts": list(self.evidence_contracts),
            "policy": self.policy,
            "produces": list(self.produces),
        }
        if self.role is not None:
            result["role"] = self.role
        if self.role_contract is not None:
            result["roleContract"] = self.role_contract
        if self.binding is not None:
            result["binding"] = self.binding
        if self.when is not None:
            result["when"] = self.when
        return result


@dataclass(frozen=True)
class Wave:
    index: int
    stages: tuple[CompiledStage, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "stages": [stage.to_dict() for stage in self.stages]}


@dataclass(frozen=True)
class ExecutionPlan:
    domain_name: str
    domain_version: str
    flow: str
    entrypoint: str | None
    input_schema: dict[str, Any]
    waves: tuple[Wave, ...]

    @property
    def stages(self) -> tuple[CompiledStage, ...]:
        return tuple(stage for wave in self.waves for stage in wave.stages)

    @property
    def stage_map(self) -> dict[str, CompiledStage]:
        return {stage.id: stage for stage in self.stages}

    def _without_digest(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "apiVersion": PLAN_API_VERSION,
            "kind": PLAN_KIND,
            "domain": {"name": self.domain_name, "version": self.domain_version},
            "flow": self.flow,
            "inputSchema": self.input_schema,
            "waves": [wave.to_dict() for wave in self.waves],
            "stageOrder": [stage.id for stage in self.stages],
        }
        if self.entrypoint is not None:
            result["entrypoint"] = self.entrypoint
        return result

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical_bytes(self._without_digest())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._without_digest()
        result["planDigest"] = self.digest
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def topological_waves(flow: Flow) -> tuple[tuple[Stage, ...], ...]:
    """Compile a DAG into maximal ready waves, preserving declaration order."""
    order = {stage.id: index for index, stage in enumerate(flow.stages)}
    stage_map = {stage.id: stage for stage in flow.stages}
    indegree = {stage.id: len(stage.needs) for stage in flow.stages}
    dependents: dict[str, list[str]] = {stage.id: [] for stage in flow.stages}
    for stage in flow.stages:
        for need in stage.needs:
            if need not in stage_map:
                raise CompileError(
                    f"flow {flow.id!r} stage {stage.id!r} depends on unknown stage {need!r}"
                )
            dependents[need].append(stage.id)

    remaining = set(stage_map)
    waves: list[tuple[Stage, ...]] = []
    while remaining:
        ready_ids = sorted(
            (stage_id for stage_id in remaining if indegree[stage_id] == 0),
            key=order.__getitem__,
        )
        if not ready_ids:
            blocked = sorted(remaining, key=order.__getitem__)
            raise CompileError(
                f"flow {flow.id!r} dependency graph contains a cycle involving: "
                + ", ".join(blocked)
            )
        waves.append(tuple(stage_map[stage_id] for stage_id in ready_ids))
        for stage_id in ready_ids:
            remaining.remove(stage_id)
            for dependent in dependents[stage_id]:
                indegree[dependent] -= 1
    return tuple(waves)


def _resolve_flow(
    pack: DomainPack, flow_id: str | None, entrypoint_id: str | None
) -> tuple[Flow, str | None]:
    if flow_id and entrypoint_id:
        raise CompileError("choose either flow or entrypoint, not both")
    if entrypoint_id:
        entrypoint = pack.entrypoint_map.get(entrypoint_id)
        if entrypoint is None:
            raise CompileError(f"unknown entrypoint {entrypoint_id!r}")
        return pack.flow_map[entrypoint.flow], entrypoint.id
    if flow_id:
        flow = pack.flow_map.get(flow_id)
        if flow is None:
            raise CompileError(f"unknown flow {flow_id!r}")
        return flow, None
    if len(pack.entrypoints) == 1:
        entrypoint = pack.entrypoints[0]
        return pack.flow_map[entrypoint.flow], entrypoint.id
    if len(pack.flows) == 1:
        return pack.flows[0], None
    raise CompileError("pack has multiple flows; specify --flow or --entrypoint")


def _compile_stage(pack: DomainPack, stage: Stage) -> CompiledStage:
    capability = pack.capability_map[stage.capability]
    policy = pack.policy_for(stage)
    role = pack.role_map.get(stage.role) if stage.role else None
    return CompiledStage(
        id=stage.id,
        description=stage.description,
        capability=capability.id,
        capability_description=capability.description,
        capability_kind=capability.kind.value,
        side_effects=capability.side_effects.value,
        input_schema=capability.input_schema,
        output_schema=capability.output_schema,
        permissions=capability.permissions,
        binding=capability.binding.to_dict() if capability.binding else None,
        role=stage.role,
        role_contract=role.to_dict() if role else None,
        needs=stage.needs,
        fanout=stage.fanout.to_dict(),
        requires_evidence=stage.requires_evidence,
        evidence_contracts=tuple(
            pack.evidence_map[evidence_id].to_dict()
            for evidence_id in stage.requires_evidence
        ),
        policy=policy.to_dict(),
        produces=stage.produces,
        when=stage.when,
    )


def compile_plan(
    pack: DomainPack, *, flow_id: str | None = None, entrypoint_id: str | None = None
) -> ExecutionPlan:
    flow, resolved_entrypoint = _resolve_flow(pack, flow_id, entrypoint_id)
    waves = tuple(
        Wave(index=index, stages=tuple(_compile_stage(pack, stage) for stage in stages))
        for index, stages in enumerate(topological_waves(flow))
    )
    return ExecutionPlan(
        domain_name=pack.metadata.name,
        domain_version=pack.metadata.version,
        flow=flow.id,
        entrypoint=resolved_entrypoint,
        input_schema=flow.input_schema,
        waves=waves,
    )


def inspect_pack(pack: DomainPack) -> dict[str, Any]:
    used_capabilities = {
        stage.capability for flow in pack.flows for stage in flow.stages
    }
    return {
        "apiVersion": pack.api_version,
        "kind": pack.kind,
        "metadata": pack.metadata.to_dict(),
        "defaultPolicy": pack.default_policy,
        "counts": {
            "capabilities": len(pack.capabilities),
            "roles": len(pack.roles),
            "evidence": len(pack.evidence),
            "policies": len(pack.policies),
            "flows": len(pack.flows),
            "entrypoints": len(pack.entrypoints),
        },
        "capabilities": [
            {
                "id": capability.id,
                "kind": capability.kind.value,
                "sideEffects": capability.side_effects.value,
                "used": capability.id in used_capabilities,
            }
            for capability in pack.capabilities
        ],
        "flows": [
            {
                "id": flow.id,
                "stageCount": len(flow.stages),
                "waves": [[stage.id for stage in wave] for wave in topological_waves(flow)],
            }
            for flow in pack.flows
        ],
        "entrypoints": [entrypoint.to_dict() for entrypoint in pack.entrypoints],
    }
