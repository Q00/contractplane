# OpenClip Domain Pack

OpenClip is ContractPlane's first substantial real-domain fixture. It packages
the public `$oc` entrypoint, private worker roles, media capabilities, approval
policies, evidence contracts, and four flow templates as one portable
`DomainPack`.

The source project remains [Q00/openclip](https://github.com/Q00/openclip). This
directory is a synchronized, licensed copy pinned by `SOURCE.lock.json`.
`bundle/` preserves OpenClip's exact self-contained distribution layout:
manifest, generated resource lock, compiled plan, and all 13 role contracts.
`openclip.yaml` is a convenience mirror of `bundle/openclip.domain.yaml` for the
ContractPlane CLI and conformance tests.

The two lock files have deliberately separate jobs: `bundle/lock.json` proves
the integrity of resources inside the OpenClip distribution, while
`SOURCE.lock.json` pins that distribution to an upstream release tag and commit.

## Current conformance level

- All four flow templates validate and compile into deterministic waves.
- `shorts` is the first checked-in golden execution-plan fixture.
- Capability bindings and permissions are declarative and inspectable.
- All 13 bound roles ship as hash-locked portable contracts under `bundle/roles/`.
- Fan-out selectors and `when` expressions are preserved, not evaluated.
- ContractPlane does not execute `oc` or agent roles in v0.1.

OpenClip remains fully standalone. It bundles the same pack and exposes it with:

```bash
oc domain-pack show
oc domain-pack export --out ./openclip-pack
```

Compile the reference flow locally:

```bash
contractplane validate domain-packs/openclip/openclip.yaml
contractplane compile domain-packs/openclip/openclip.yaml \
  --entrypoint shorts --out /tmp/openclip-shorts.plan.json
```

Maintainers refresh the pinned bundle only from a clean, tagged OpenClip
checkout:

```bash
uv run python scripts/sync_openclip_pack.py \
  --source ../video --require-release
```

The next adapter milestone is to expand the plan's chunk, section, and hook
selectors into stable `UnitRef` keys, invoke the published `oc` JSON CLI, and
mirror scoped ContractPlane directives into `oc steer` without merging the two
projects' ledgers.
