# Changelog

All notable changes to this project are documented here. The project follows
Semantic Versioning once the v2 runtime leaves development status.

## [Unreleased]

The current package version is the `2.0.0b1` release candidate. A matching
`v2.0.0-beta.1` tag triggers the gated GitHub prerelease workflow.

### Added

- Standard `pyproject.toml` packaging with installed runtime and doctor CLIs.
- A `gemini` optional dependency that requires the current `google-genai` 2.x API.
- Installed-CLI verification in the Python 3.9, 3.12, and 3.13 CI matrix.
- Distribution build verification, vulnerability auditing, and weekly
  dependency update checks.
- An 80% core branch-coverage floor and one-command no-network release gate.
- Ruff correctness and import-hygiene checks in local and hosted release gates.
- A tag-version-locked GitHub prerelease workflow that uploads verified wheel
  and source distributions.
- Exa enabled as an anti-lock-in and verification route after a bounded paired
  benchmark demonstrated material unique-index gain over Brave.

### Fixed

- CI now installs declared dependencies before testing `.env` behavior.
- The doctor reports incompatible package versions instead of treating every
  importable Gemini SDK as ready.
- `.env.example` documents the v2 Brave adapter's actual
  `BRAVE_SEARCH_API_KEY` variable.
- Legacy async-worker tests now cover Gemini terminal extraction and pending-job
  ledger clearing without calling a provider.
