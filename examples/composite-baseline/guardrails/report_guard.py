#!/usr/bin/env python3
"""Guardrails AI equivalent of the report-artifact contract (EXPERIMENTAL).

Runtime LLM-output validator baseline for examples/composite-baseline, using the
`guardrails-ai` library the paper cites as [cite:guardrails]. This module MUST be
run under the isolated composite venv
(.ouroboros/composite-venv/bin/python), where guardrails-ai is installed; the
repo's main .venv deliberately does not carry it. The driver run_guardrails.py
invokes this file as a subprocess.

SCOPE / HONESTY: this uses ONLY guardrails' core, OFFLINE, Pydantic-based
structural validation (types, required fields, value constraints). It does NOT
use any guardrails Hub validator, because installing hub validators
(`guardrails hub install ...`) requires network/auth; none is used here. That is
the honest, apples-to-apples surface for "what the framework provides out of the
box without external services." A Guard built this way enforces the SAME
structure the contractplane report-artifact evidence schema enforces
(dataset:str, rows:int>=1, generatedBy=="compile-report").

CLI: report_guard.py <claims.json> — claims.json is a list of {"id","artifact"};
prints a JSON list of {"id","guard_passed","error"} to stdout.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Literal

os.environ.setdefault("GUARDRAILS_DISABLE_TELEMETRY", "true")
os.environ.setdefault("GUARDRAILS_TELEMETRY_ENABLED", "false")

from pydantic import BaseModel, Field  # noqa: E402
from guardrails import Guard  # noqa: E402


class ReportArtifact(BaseModel):
    """Mirror of the contractplane report-artifact evidence schema."""

    dataset: str = Field(min_length=1)
    rows: int = Field(ge=1)
    generatedBy: Literal["compile-report"]


def build_guard() -> Guard:
    return Guard.for_pydantic(ReportArtifact)


def evaluate(guard: Guard, artifact: dict) -> dict:
    """Return {'guard_passed': bool, 'error': str|None} for one artifact."""
    try:
        outcome = guard.parse(llm_output=json.dumps(artifact))
        passed = bool(outcome.validation_passed)
        error = None
        if not passed:
            summaries = getattr(outcome, "validation_summaries", None) or []
            error = "; ".join(str(getattr(s, "failure_reason", s)) for s in summaries) or "structure/schema validation failed"
        return {"guard_passed": passed, "error": error}
    except Exception as exc:  # guardrails raises on some structural failures
        return {"guard_passed": False, "error": f"{type(exc).__name__}: {exc}"}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: report_guard.py <claims.json>", file=sys.stderr)
        return 2
    claims = json.loads(open(argv[1], encoding="utf-8").read())
    guard = build_guard()
    results = []
    for claim in claims:
        verdict = evaluate(guard, claim["artifact"])
        results.append({"id": claim["id"], **verdict})
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
