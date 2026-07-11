#!/usr/bin/env python3
"""Synchronize the complete, released OpenClip Domain Pack bundle.

OpenClip owns the canonical manifest, role contracts, resource lock, and
compiled reference plans. ContractPlane keeps a provenance-pinned copy for
examples and conformance. ``--check`` is read-only; ``--require-release``
rejects a source checkout whose HEAD is not tagged with its package version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from contractplane.compiler import compile_plan
from contractplane.loader import load_domain_pack

ROOT = Path(__file__).resolve().parent.parent
DEST_ROOT = ROOT / "domain-packs" / "openclip"
DEST_BUNDLE = DEST_ROOT / "bundle"
DEST_PACK = DEST_ROOT / "openclip.yaml"
DEST_SOURCE_LOCK = DEST_ROOT / "SOURCE.lock.json"
DEST_PLAN = ROOT / "conformance" / "openclip" / "flow2-shorts.plan.json"
CANONICAL_REPOSITORY = "https://github.com/Q00/openclip"


def _source_root(value: str | None) -> Path:
    raw = value or os.environ.get("OPENCLIP_SOURCE") or str(ROOT.parent / "video")
    return Path(raw).expanduser().resolve()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative(value: object) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"bundle resource path must be a string, got {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe bundle resource path: {value!r}")
    return Path(*path.parts)


def _plan_digest(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("planDigest", None)
    canonical = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha(canonical)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _git(source_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _project_version(source_root: Path) -> str:
    with (source_root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _source_provenance(
    source_root: Path, *, require_release: bool
) -> dict[str, str]:
    dirty = _git(source_root, "status", "--porcelain")
    if dirty:
        raise ValueError("OpenClip source checkout must be clean before synchronization")

    version = _project_version(source_root)
    expected_tag = f"v{version}"
    commit = _git(source_root, "rev-parse", "HEAD")
    tags = set(filter(None, _git(source_root, "tag", "--points-at", "HEAD").splitlines()))
    release = expected_tag if expected_tag in tags else "unreleased"
    if require_release and release == "unreleased":
        raise ValueError(
            f"OpenClip HEAD is not tagged {expected_tag}; release it before pinning provenance"
        )
    if require_release:
        origin = _git(source_root, "remote", "get-url", "origin")
        accepted_origins = {
            "https://github.com/Q00/openclip",
            "https://github.com/Q00/openclip.git",
            "git@github.com:Q00/openclip.git",
        }
        if origin not in accepted_origins:
            raise ValueError(f"OpenClip origin is not the canonical repository: {origin}")
        remote_lines = _git(
            source_root,
            "ls-remote",
            "--tags",
            "origin",
            f"refs/tags/{expected_tag}",
            f"refs/tags/{expected_tag}^{{}}",
        ).splitlines()
        remote_refs = {
            ref: sha
            for line in remote_lines
            for sha, ref in [line.split("\t", 1)]
        }
        remote_commit = remote_refs.get(f"refs/tags/{expected_tag}^{{}}") or remote_refs.get(
            f"refs/tags/{expected_tag}"
        )
        if remote_commit != commit:
            raise ValueError(
                f"remote tag {expected_tag} resolves to {remote_commit!r}, not source HEAD {commit}"
            )
    return {
        "repository": CANONICAL_REPOSITORY,
        "release": release,
        "version": version,
        "baseCommit": commit,
        "path": "contractplane/openclip.domain.yaml",
        "bundleLockPath": "contractplane/lock.json",
    }


def _verified_bundle(
    source_root: Path,
) -> tuple[dict[str, Any], dict[Path, bytes], bytes]:
    source_bundle = source_root / "contractplane"
    lock_path = source_bundle / "lock.json"
    lock = _read_json(lock_path)
    if lock.get("schema") != "openclip-contractplane-lock-v2":
        raise ValueError(f"unsupported OpenClip bundle lock: {lock.get('schema')!r}")
    if lock.get("domain") != "openclip":
        raise ValueError(f"unexpected OpenClip bundle domain: {lock.get('domain')!r}")

    resources: dict[Path, bytes] = {Path("lock.json"): lock_path.read_bytes()}

    def add(path_value: object, expected_sha: object, label: str) -> bytes:
        relative = _safe_relative(path_value)
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise ValueError(f"{label} has no valid sha256")
        source = source_bundle / relative
        if source.is_symlink() or not source.is_file():
            raise FileNotFoundError(f"locked OpenClip resource is missing: {source}")
        body = source.read_bytes()
        actual = _sha(body)
        if actual != expected_sha:
            raise ValueError(
                f"{label} sha256 mismatch for {relative}: expected {expected_sha}, got {actual}"
            )
        resources[relative] = body
        return body

    manifest = add("openclip.domain.yaml", lock.get("packSha256"), "manifest")

    roles = lock.get("roleContracts")
    if not isinstance(roles, list) or len(roles) != 13:
        raise ValueError("OpenClip bundle must lock exactly 13 role contracts")
    for index, item in enumerate(roles):
        if not isinstance(item, dict):
            raise ValueError(f"roleContracts[{index}] must be an object")
        add(item.get("path"), item.get("sha256"), f"roleContracts[{index}]")

    plans = lock.get("compiledPlans")
    if not isinstance(plans, list) or not plans:
        raise ValueError("OpenClip bundle must lock at least one compiled plan")
    shorts_body: bytes | None = None
    for index, item in enumerate(plans):
        if not isinstance(item, dict):
            raise ValueError(f"compiledPlans[{index}] must be an object")
        body = add(item.get("path"), item.get("sha256"), f"compiledPlans[{index}]")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError(f"compiledPlans[{index}] root must be an object")
        digest = payload.get("planDigest")
        if digest != item.get("planDigest") or digest != _plan_digest(payload):
            raise ValueError(f"compiledPlans[{index}] has an invalid planDigest")
        if item.get("flow") == "shorts" and item.get("entrypoint") == "shorts":
            shorts_body = body

    if shorts_body is None:
        raise ValueError("OpenClip bundle has no locked shorts reference plan")

    pack = load_domain_pack(source_bundle / "openclip.domain.yaml")
    compiled = compile_plan(pack, entrypoint_id="shorts").to_json().encode("utf-8")
    if json.loads(compiled) != json.loads(shorts_body):
        raise ValueError("OpenClip shorts plan is stale for the bundled manifest")
    return lock, resources, compiled


def _source_lock(
    provenance: dict[str, str],
    bundle_lock: dict[str, Any],
    resources: dict[Path, bytes],
    compiled: bytes,
) -> bytes:
    roles = [
        {
            "role": item["role"],
            "path": f"domain-packs/openclip/bundle/{item['path']}",
            "sha256": item["sha256"],
        }
        for item in bundle_lock["roleContracts"]
    ]
    compiled_payload = json.loads(compiled)
    payload = {
        "schema": "contractplane-domain-source-lock-v2",
        "domain": "openclip",
        "source": provenance,
        "packSha256": bundle_lock["packSha256"],
        "bundleLock": {
            "path": "domain-packs/openclip/bundle/lock.json",
            "sha256": _sha(resources[Path("lock.json")]),
        },
        "roleContracts": roles,
        "compiledFixture": {
            "path": "conformance/openclip/flow2-shorts.plan.json",
            "sha256": _sha(compiled),
            "planDigest": compiled_payload["planDigest"],
        },
    }
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sync(source_root: Path, *, check: bool, require_release: bool) -> int:
    bundle_lock, resources, compiled = _verified_bundle(source_root)
    provenance = _source_provenance(source_root, require_release=require_release)
    manifest = resources[Path("openclip.domain.yaml")]
    desired: dict[Path, bytes] = {
        DEST_PACK: manifest,
        DEST_PLAN: compiled,
    }
    for relative, body in resources.items():
        desired[DEST_BUNDLE / relative] = body
    desired[DEST_SOURCE_LOCK] = _source_lock(
        provenance, bundle_lock, resources, compiled
    )

    stale = [
        path
        for path, body in desired.items()
        if not path.is_file() or path.read_bytes() != body
    ]
    expected_bundle = {
        (DEST_BUNDLE / relative).resolve() for relative in resources
    }
    extra = (
        [
            path
            for path in DEST_BUNDLE.rglob("*")
            if path.is_file() and path.resolve() not in expected_bundle
        ]
        if DEST_BUNDLE.exists()
        else []
    )

    if check:
        if stale or extra:
            print(
                json.dumps(
                    {
                        "synced": False,
                        "stale": [str(path) for path in stale],
                        "extra": [str(path) for path in extra],
                    },
                    sort_keys=True,
                )
            )
            return 1
    else:
        for path in extra:
            path.unlink()
        for path, body in desired.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)

    print(
        json.dumps(
            {
                "synced": True,
                "release": provenance["release"],
                "baseCommit": provenance["baseCommit"],
                "packSha256": _sha(manifest),
                "planDigest": json.loads(compiled)["planDigest"],
                "resources": len(resources),
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="path to an OpenClip checkout")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--require-release",
        action="store_true",
        help="require HEAD to carry the v<project-version> tag",
    )
    args = parser.parse_args()
    return sync(
        _source_root(args.source),
        check=args.check,
        require_release=args.require_release,
    )


if __name__ == "__main__":
    raise SystemExit(main())
