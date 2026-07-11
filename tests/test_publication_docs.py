from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_MARKDOWN = (
    ROOT / "README.md",
    ROOT / "STATUS.md",
    ROOT / "WHITEPAPER.md",
    ROOT / "SECURITY.md",
    ROOT / "GOVERNANCE.md",
    ROOT / "docs" / "design" / "requirements.md",
    ROOT / "docs" / "design" / "architecture.md",
    ROOT / "docs" / "design" / "mastra-comparison.md",
    ROOT / "rfds" / "0001-core-model.md",
    ROOT / "examples" / "openclip-local" / "README.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_local_markdown_links_resolve() -> None:
    link = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    missing: list[str] = []
    for document in PUBLIC_MARKDOWN:
        for target in link.findall(_read(document)):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            path_text = target.split("#", 1)[0]
            if not path_text:
                continue
            resolved = (document.parent / path_text).resolve()
            if not resolved.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert missing == []


def test_publication_status_does_not_overclaim_v0_1() -> None:
    readme = _read(ROOT / "README.md")
    status = _read(ROOT / "STATUS.md")
    whitepaper = _read(ROOT / "WHITEPAPER.md")
    site = _read(ROOT / "site" / "index.html")
    llms = _read(ROOT / "site" / "llms.txt")

    required_limits = (
        "does not invoke",
        "independent Verdict",
        "steering invalidation",
        "canary",
        "rollback",
    )
    combined = "\n".join((readme, status, whitepaper, site, llms))
    for phrase in required_limits:
        assert phrase in combined

    assert "A claim is not confirmation" in readme
    assert "A claim is not confirmation" in site
    assert "A claim is not a state transition" not in combined
    assert "safely self-improving" not in site
    assert "RFD 0001 is Proposed" in status
    assert "DomainPack schema is an alpha candidate" in status
    assert "contractplane.dev/kernel-state/v0alpha1" in status


def test_plan_is_not_published_as_a_resolved_execution_contract() -> None:
    example = _read(ROOT / "examples" / "openclip-local" / "README.md")
    assert "`ExecutionPlan`, not a fully resolved\nExecution Contract" in example


def test_rfd_and_security_status_are_explicit() -> None:
    rfd = _read(ROOT / "rfds" / "0001-core-model.md")
    security = _read(ROOT / "SECURITY.md")
    assert "| Status | Proposed |" in rfd
    assert "This RFD is Proposed and non-normative" in rfd
    assert "security/advisories/new" in security
    assert "Private security contact requested" in security


def test_site_links_to_the_candidate_schema_and_names_neighbor_protocols() -> None:
    site = _read(ROOT / "site" / "index.html")
    llms = _read(ROOT / "site" / "llms.txt")
    schema_url = "https://contractplane.dev/spec/v1alpha1/domainpack.schema.json"
    assert schema_url in site
    assert schema_url in llms
    for text in (site, llms):
        assert "Agent Client Protocol" in text
        assert "IBM/BeeAI-origin Agent Communication Protocol" in text
        assert "part of A2A" in text


def test_github_actions_are_commit_pinned() -> None:
    uses_pattern = re.compile(r"^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)", re.MULTILINE)
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        actions = uses_pattern.findall(_read(workflow))
        assert actions, f"{workflow.name} has no actions to inspect"
        for action, revision in actions:
            assert re.fullmatch(r"[0-9a-f]{40}", revision), (
                f"{workflow.name}: {action}@{revision} is not pinned to a full commit"
            )
