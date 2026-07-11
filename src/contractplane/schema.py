from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import API_VERSION, KIND

SCHEMA_ID = "https://contractplane.dev/spec/v1alpha1/domainpack.schema.json"
ID_PATTERN = r"^[a-z][a-z0-9-]{1,62}$"


def _string_list(*, min_items: int = 0, unique: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "minItems": min_items,
    }
    if unique:
        result["uniqueItems"] = True
    return result


def _id() -> dict[str, Any]:
    return {"type": "string", "pattern": ID_PATTERN}


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def domain_pack_schema() -> dict[str, Any]:
    """Return the v1alpha1 alpha-candidate schema as a deterministic mapping."""
    definitions = {
        "metadata": _object(
            {
                "name": _id(),
                "version": {"type": "string", "minLength": 1},
                "description": {"type": "string", "minLength": 1},
            },
            ["name", "version", "description"],
        ),
        "capabilityBinding": _object(
            {
                "adapter": {
                    **_id(),
                    "description": "Adapter family name; v0.1 preserves but never invokes it.",
                },
                "target": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Opaque adapter target, never interpreted as a shell command.",
                },
                "config": {
                    "type": "object",
                    "description": "Opaque adapter configuration preserved in compiled plans.",
                },
            },
            ["adapter", "target"],
        ),
        "capability": _object(
            {
                "id": _id(),
                "kind": {"enum": ["deterministic", "agent", "integration"]},
                "description": {"type": "string", "minLength": 1},
                "sideEffects": {"enum": ["none", "local", "external"]},
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
                "permissions": {
                    **_string_list(),
                    "description": "Declared capabilities an adapter must authorize before invocation.",
                },
                "binding": {"$ref": "#/$defs/capabilityBinding"},
            },
            [
                "id",
                "kind",
                "description",
                "sideEffects",
                "inputSchema",
                "outputSchema",
                "permissions",
            ],
        ),
        "role": _object(
            {
                "id": _id(),
                "description": {"type": "string", "minLength": 1},
                "capabilities": _string_list(min_items=1),
                "instructions": {"type": "string", "minLength": 1},
            },
            ["id", "description", "capabilities", "instructions"],
        ),
        "evidence": _object(
            {
                "id": _id(),
                "kind": {
                    "enum": ["json-schema", "artifact", "semantic-review", "external-receipt"]
                },
                "description": {"type": "string", "minLength": 1},
                "schema": {"type": "object"},
            },
            ["id", "kind", "description"],
        ),
        "policy": _object(
            {
                "id": _id(),
                "description": {"type": "string", "minLength": 1},
                "evidenceRequired": {"type": "boolean"},
                "humanApproval": {"enum": ["never", "always"]},
                "maxAttempts": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["id", "description", "evidenceRequired", "humanApproval", "maxAttempts"],
        ),
        "fanout": _object(
            {
                "mode": {"enum": ["singleton", "each"]},
                "over": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Opaque fanout selector preserved by v0.1. Adapters or a future "
                        "PlanBuilder expand it into UnitRef values."
                    ),
                },
            },
            ["mode"],
        ),
        "stage": _object(
            {
                "id": _id(),
                "description": {"type": "string", "minLength": 1},
                "capability": _id(),
                "role": _id(),
                "needs": _string_list(),
                "fanout": {"$ref": "#/$defs/fanout"},
                "requiresEvidence": _string_list(),
                "policy": _id(),
                "produces": _string_list(),
                "when": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Declarative condition expression preserved but never evaluated by the v0.1 kernel."
                    ),
                },
            },
            [
                "id",
                "description",
                "capability",
                "needs",
                "fanout",
                "requiresEvidence",
                "produces",
            ],
        ),
        "flow": _object(
            {
                "id": _id(),
                "description": {"type": "string", "minLength": 1},
                "inputSchema": {"type": "object"},
                "stages": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/stage"},
                    "minItems": 1,
                },
            },
            ["id", "description", "inputSchema", "stages"],
        ),
        "entryPoint": _object(
            {
                "id": _id(),
                "description": {"type": "string", "minLength": 1},
                "flow": _id(),
                "keywords": _string_list(min_items=1),
                "examples": _string_list(min_items=1),
            },
            ["id", "description", "flow", "keywords", "examples"],
        ),
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "ContractPlane DomainPack v1alpha1",
        "description": "Portable contracts for evidence-gated agent workflows.",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "apiVersion": {"const": API_VERSION},
            "kind": {"const": KIND},
            "metadata": {"$ref": "#/$defs/metadata"},
            "defaultPolicy": _id(),
            "capabilities": {
                "type": "array",
                "items": {"$ref": "#/$defs/capability"},
                "minItems": 1,
            },
            "roles": {"type": "array", "items": {"$ref": "#/$defs/role"}},
            "evidence": {
                "type": "array",
                "items": {"$ref": "#/$defs/evidence"},
                "minItems": 1,
            },
            "policies": {
                "type": "array",
                "items": {"$ref": "#/$defs/policy"},
                "minItems": 1,
            },
            "flows": {
                "type": "array",
                "items": {"$ref": "#/$defs/flow"},
                "minItems": 1,
            },
            "entrypoints": {
                "type": "array",
                "items": {"$ref": "#/$defs/entryPoint"},
                "minItems": 1,
            },
        },
        "required": [
            "apiVersion",
            "kind",
            "metadata",
            "defaultPolicy",
            "capabilities",
            "roles",
            "evidence",
            "policies",
            "flows",
            "entrypoints",
        ],
        "$defs": definitions,
    }


def schema_json() -> str:
    return json.dumps(domain_pack_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_schema(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(schema_json(), encoding="utf-8")
    return target
