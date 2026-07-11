from __future__ import annotations

import json
from pathlib import Path

from contractplane import __version__
from contractplane.cli import main

ROOT = Path(__file__).resolve().parents[1]
HELLO = ROOT / "examples" / "hello-domain" / "domainpack.yaml"


def test_validate_and_inspect_commands(capsys) -> None:
    assert main(["validate", str(HELLO)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is True and result["name"] == "hello-domain"

    assert main(["inspect", str(HELLO)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["flows"][0]["waves"][2] == ["publish", "archive"]


def test_compile_stdout_and_file_are_deterministic(tmp_path: Path, capsys) -> None:
    assert main(["compile", str(HELLO), "--entrypoint", "hello"]) == 0
    stdout_plan = json.loads(capsys.readouterr().out)
    target = tmp_path / "plan.json"
    assert main(
        ["compile", str(HELLO), "--entrypoint", "hello", "--out", str(target)]
    ) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["planDigest"] == stdout_plan["planDigest"]
    assert json.loads(target.read_text(encoding="utf-8")) == stdout_plan


def test_invalid_pack_prints_structured_error_and_nonzero(capsys) -> None:
    invalid = ROOT / "conformance" / "invalid" / "missing-evidence.yaml"
    assert main(["validate", str(invalid)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["valid"] is False
    assert error["error"] == "DomainPackValidationError"


def test_schema_command_can_write_normative_schema(tmp_path: Path, capsys) -> None:
    target = tmp_path / "schema.json"
    assert main(["schema", "--out", str(target)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["written"] == str(target.resolve())
    assert json.loads(target.read_text(encoding="utf-8"))["title"].endswith("v1alpha1")


def test_version_constant_is_v0_1() -> None:
    assert __version__ == "0.1.0a1"
