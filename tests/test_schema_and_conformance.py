from __future__ import annotations

import json
from pathlib import Path

import pytest

from contractplane.errors import DomainPackValidationError
from contractplane.compiler import compile_plan
from contractplane.loader import load_domain_pack
from contractplane.schema import domain_pack_schema, schema_json

ROOT = Path(__file__).resolve().parents[1]


def test_generated_schema_is_deterministic_and_matches_checked_in_spec() -> None:
    first = schema_json()
    second = schema_json()
    assert first == second
    checked_in = ROOT / "spec" / "v1alpha1" / "domainpack.schema.json"
    assert checked_in.read_text(encoding="utf-8") == first
    assert json.loads(first) == domain_pack_schema()


def test_conformance_corpus() -> None:
    valid = sorted((ROOT / "conformance" / "valid").glob("*.yaml"))
    invalid = sorted((ROOT / "conformance" / "invalid").glob("*.yaml"))
    assert valid and invalid
    for path in valid:
        assert load_domain_pack(path).kind == "DomainPack"
    for path in invalid:
        with pytest.raises(DomainPackValidationError):
            load_domain_pack(path)


def test_conformance_compiler_golden_file() -> None:
    pack = load_domain_pack(ROOT / "conformance" / "valid" / "hello-domain.yaml")
    actual = compile_plan(pack, entrypoint_id="hello").to_dict()
    expected = json.loads(
        (ROOT / "conformance" / "expected" / "hello-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert actual == expected


def test_reference_kernel_contains_no_shell_execution_runtime() -> None:
    forbidden = ("subprocess", "os.system", "shell=True", "create_subprocess")
    for source in sorted((ROOT / "src" / "contractplane").glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{source.name} unexpectedly contains {marker!r}"
