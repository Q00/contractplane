from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

API_VERSION = "contractplane.dev/v1alpha1"
KIND = "DomainPack"


class CapabilityKind(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENT = "agent"
    INTEGRATION = "integration"


class SideEffect(StrEnum):
    NONE = "none"
    LOCAL = "local"
    EXTERNAL = "external"


class EvidenceKind(StrEnum):
    JSON_SCHEMA = "json-schema"
    ARTIFACT = "artifact"
    SEMANTIC_REVIEW = "semantic-review"
    EXTERNAL_RECEIPT = "external-receipt"


class HumanApproval(StrEnum):
    NEVER = "never"
    ALWAYS = "always"


class FanoutMode(StrEnum):
    SINGLETON = "singleton"
    EACH = "each"


@dataclass(frozen=True)
class Metadata:
    name: str
    version: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description}


@dataclass(frozen=True)
class CapabilityBinding:
    adapter: str
    target: str
    config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"adapter": self.adapter, "target": self.target}
        if self.config is not None:
            result["config"] = self.config
        return result


@dataclass(frozen=True)
class Capability:
    id: str
    kind: CapabilityKind
    description: str
    side_effects: SideEffect
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: tuple[str, ...]
    binding: CapabilityBinding | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind.value,
            "description": self.description,
            "sideEffects": self.side_effects.value,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "permissions": list(self.permissions),
        }
        if self.binding is not None:
            result["binding"] = self.binding.to_dict()
        return result


@dataclass(frozen=True)
class Role:
    id: str
    description: str
    capabilities: tuple[str, ...]
    instructions: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "instructions": self.instructions,
        }


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: EvidenceKind
    description: str
    schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind.value,
            "description": self.description,
        }
        if self.schema is not None:
            result["schema"] = self.schema
        return result


@dataclass(frozen=True)
class Policy:
    id: str
    description: str
    evidence_required: bool
    human_approval: HumanApproval
    max_attempts: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "evidenceRequired": self.evidence_required,
            "humanApproval": self.human_approval.value,
            "maxAttempts": self.max_attempts,
        }


@dataclass(frozen=True)
class Fanout:
    mode: FanoutMode
    over: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"mode": self.mode.value}
        if self.over is not None:
            result["over"] = self.over
        return result


@dataclass(frozen=True)
class Stage:
    id: str
    description: str
    capability: str
    role: str | None
    needs: tuple[str, ...]
    fanout: Fanout
    requires_evidence: tuple[str, ...]
    policy: str | None
    produces: tuple[str, ...]
    when: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "capability": self.capability,
            "needs": list(self.needs),
            "fanout": self.fanout.to_dict(),
            "requiresEvidence": list(self.requires_evidence),
            "produces": list(self.produces),
        }
        if self.role is not None:
            result["role"] = self.role
        if self.policy is not None:
            result["policy"] = self.policy
        if self.when is not None:
            result["when"] = self.when
        return result


@dataclass(frozen=True)
class Flow:
    id: str
    description: str
    input_schema: dict[str, Any]
    stages: tuple[Stage, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "inputSchema": self.input_schema,
            "stages": [stage.to_dict() for stage in self.stages],
        }


@dataclass(frozen=True)
class EntryPoint:
    id: str
    description: str
    flow: str
    keywords: tuple[str, ...]
    examples: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "flow": self.flow,
            "keywords": list(self.keywords),
            "examples": list(self.examples),
        }


@dataclass(frozen=True)
class DomainPack:
    api_version: str
    kind: str
    metadata: Metadata
    default_policy: str
    capabilities: tuple[Capability, ...]
    roles: tuple[Role, ...]
    evidence: tuple[Evidence, ...]
    policies: tuple[Policy, ...]
    flows: tuple[Flow, ...]
    entrypoints: tuple[EntryPoint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "defaultPolicy": self.default_policy,
            "capabilities": [item.to_dict() for item in self.capabilities],
            "roles": [item.to_dict() for item in self.roles],
            "evidence": [item.to_dict() for item in self.evidence],
            "policies": [item.to_dict() for item in self.policies],
            "flows": [item.to_dict() for item in self.flows],
            "entrypoints": [item.to_dict() for item in self.entrypoints],
        }

    @property
    def capability_map(self) -> dict[str, Capability]:
        return {item.id: item for item in self.capabilities}

    @property
    def role_map(self) -> dict[str, Role]:
        return {item.id: item for item in self.roles}

    @property
    def evidence_map(self) -> dict[str, Evidence]:
        return {item.id: item for item in self.evidence}

    @property
    def policy_map(self) -> dict[str, Policy]:
        return {item.id: item for item in self.policies}

    @property
    def flow_map(self) -> dict[str, Flow]:
        return {item.id: item for item in self.flows}

    @property
    def entrypoint_map(self) -> dict[str, EntryPoint]:
        return {item.id: item for item in self.entrypoints}

    def policy_for(self, stage: Stage) -> Policy:
        return self.policy_map[stage.policy or self.default_policy]
