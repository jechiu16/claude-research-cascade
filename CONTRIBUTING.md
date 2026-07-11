# Contributing

Contributions are welcome when they preserve the runtime's mechanical
guarantees and host neutrality.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,gemini]"
.venv/bin/deep-research-release-gate
```

## Pull requests

- Keep the root `SKILL.md` host-neutral. Claude Code and Codex wrappers may map
  discovery or native tools, but must not fork the protocol.
- Add fixture-first tests for provider adapters. A credential is not adoption
  evidence, and a provider stays disabled until its request boundary and policy
  gates pass.
- Never commit credentials, unrestricted provider payloads, or user material.
- Preserve one permit per physical request, no automatic paid resubmission,
  spool-before-parse, canonical state, and fail-closed validation.
- Update English and Traditional Chinese user-facing documentation together.
- Run the complete release gate from a clean worktree before requesting review.

Provider adoption or live benchmarks require an explicit request-count and cost
envelope from the person authorizing the run.
