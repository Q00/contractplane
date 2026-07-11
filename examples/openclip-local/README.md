# Use the OpenClip pack locally

Install the released OpenClip tool surface and run ContractPlane from this repo:

```bash
uv tool install "openclip-agent==0.2.4"
uv sync --extra dev
uv run contractplane inspect domain-packs/openclip/openclip.yaml
uv run contractplane compile domain-packs/openclip/openclip.yaml --entrypoint shorts
```

The compiler output is an inspectable `ExecutionPlan`, not a fully resolved
Execution Contract. ContractPlane `v0.1` does not evaluate its selectors or
conditions and does not invoke its bindings. Continue to invoke OpenClip through
`$oc` or the `oc` CLI until the OpenClip adapter reaches conformance.
