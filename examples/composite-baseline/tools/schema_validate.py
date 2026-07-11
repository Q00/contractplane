#!/usr/bin/env python3
"""Schema-gate step of the COMPOSITE baseline (EXPERIMENTAL).

The PROV/OPA/CWL composite has no built-in notion of "evidence": a schema check
is an ordinary workflow step the integrator must remember to wire in. This tool
validates the producer's artifact against a JSON Schema (the composite analogue
of the contractplane ``report-artifact`` evidence schema) using the stdlib only.

Exit 0 and copy the artifact forward on success; exit 1 (which cwltool turns
into a permanentFail, i.e. a RED pipeline) on any schema violation — so a
format-violation is caught *here*, before recomputation is ever consulted,
mirroring the layered gate on the contractplane side.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _validate(artifact: dict, schema: dict) -> list[str]:
    """A deliberately small JSON-Schema subset: required, type, const, minimum,
    additionalProperties=false. Enough for the report-artifact contract."""
    errors: list[str] = []
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in artifact:
            errors.append(f"missing required field {key!r}")
    if schema.get("additionalProperties") is False:
        for key in artifact:
            if key not in props:
                errors.append(f"unexpected field {key!r}")
    for key, spec in props.items():
        if key not in artifact:
            continue
        value = artifact[key]
        want = spec.get("type")
        if want == "string" and not isinstance(value, str):
            errors.append(f"field {key!r} must be a string")
        if want == "integer" and not isinstance(value, int):
            errors.append(f"field {key!r} must be an integer")
        if "const" in spec and value != spec["const"]:
            errors.append(f"field {key!r} must equal {spec['const']!r}")
        if "minimum" in spec and isinstance(value, int) and value < spec["minimum"]:
            errors.append(f"field {key!r} must be >= {spec['minimum']}")
        if "minLength" in spec and isinstance(value, str) and len(value) < spec["minLength"]:
            errors.append(f"field {key!r} must have length >= {spec['minLength']}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: schema_validate.py <artifact.json> <schema.json>", file=sys.stderr)
        return 2
    artifact = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    schema = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    errors = _validate(artifact, schema)
    if errors:
        print("schema-gate REJECT: " + "; ".join(errors), file=sys.stderr)
        return 1
    Path("checked.json").write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print("schema-gate PASS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
