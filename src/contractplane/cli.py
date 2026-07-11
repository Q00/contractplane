from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .compiler import compile_plan, inspect_pack
from .errors import ContractPlaneError, DomainPackValidationError
from .loader import load_domain_pack
from .schema import schema_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contractplane",
        description="Validate and compile portable, evidence-gated agent contracts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a DomainPack")
    validate.add_argument("pack", help="path to DomainPack YAML or JSON")

    inspect = commands.add_parser("inspect", help="inspect validated pack topology")
    inspect.add_argument("pack", help="path to DomainPack YAML or JSON")

    compile_command = commands.add_parser(
        "compile", help="compile one flow into deterministic topological waves"
    )
    compile_command.add_argument("pack", help="path to DomainPack YAML or JSON")
    selector = compile_command.add_mutually_exclusive_group()
    selector.add_argument("--flow", help="flow id to compile")
    selector.add_argument("--entrypoint", help="entrypoint id to resolve and compile")
    compile_command.add_argument("--out", help="write the compiled plan JSON to this path")

    schema = commands.add_parser(
        "schema", help="print the v1alpha1 alpha-candidate DomainPack JSON Schema"
    )
    schema.add_argument("--out", help="write the JSON Schema to this path")
    return parser


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write(path: str, content: str) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _dispatch(args: argparse.Namespace) -> dict[str, Any] | str:
    if args.command == "schema":
        content = schema_json()
        if args.out:
            target = _write(args.out, content)
            return {"schema": "contractplane.dev/v1alpha1", "written": str(target)}
        return content

    pack = load_domain_pack(args.pack)
    if args.command == "validate":
        return {
            "valid": True,
            "apiVersion": pack.api_version,
            "kind": pack.kind,
            "name": pack.metadata.name,
            "version": pack.metadata.version,
        }
    if args.command == "inspect":
        return inspect_pack(pack)
    if args.command == "compile":
        plan = compile_plan(pack, flow_id=args.flow, entrypoint_id=args.entrypoint)
        if args.out:
            target = _write(args.out, plan.to_json())
            return {
                "compiled": True,
                "flow": plan.flow,
                "planDigest": plan.digest,
                "written": str(target),
            }
        return plan.to_dict()
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _dispatch(args)
    except DomainPackValidationError as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "error": "DomainPackValidationError",
                    "issues": [issue.to_dict() for issue in exc.issues],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except ContractPlaneError as exc:
        print(
            json.dumps(
                {"error": exc.__class__.__name__, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    if isinstance(result, str):
        sys.stdout.write(result)
    else:
        sys.stdout.write(_pretty(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
