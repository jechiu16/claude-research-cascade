# Changelog

All notable changes to this project are documented here. The project follows
Semantic Versioning once the v2 runtime leaves development status.

## 2.0.0b5

### Added

- A deterministic human readiness table for `deep-research-state providers`
  that hides contract-test and test-only routes while keeping `providers --json`
  machine-compatible.
- A single real first-use path in the English and Traditional Chinese READMEs,
  covering the optional demo, readiness, host discovery, session restart,
  `/deep`, and contract confirmation.

### Changed

- Traditional Chinese deterministic HTML report chrome now preserves the
  `zh-Hant-TW` presentation contract.
- Permit/action-id traversal hardening now validates request identity and refuses
  redirects that could create an unapproved physical request.

### Fixed

- The OpenAI Deep Research storage note now records enablement after the
  2026-07-12 live adoption occurrence.
- Release metadata now aligns the package version and release-gate documentation
  for Beta 5, including Ruff static checks without obsolete golden-transcript
  validation.

## 2.0.0b4

### Added

- A `promote` CLI subcommand and `promote_provider_payload` artifact
  pipeline that turns a completed provider retrieval occurrence's
  boundary-spooled payload into an indexed, provenance-bound artifact,
  without ever letting a caller name an arbitrary filesystem path for
  provider bytes.
- A `citations` CLI subcommand: a free, read-only harvest of every citation
  recorded on retrieval occurrences (optionally scoped to one action),
  deduplicated by url and flagged `directly_verified` against `sources`
  with a matching directly fetched url. Verification-stage sampling reads
  this list to choose which citation to fetch directly next.
- `scripts/calibration_report.py`, a pure offline reader that turns
  finished session directories and an optional human-authored annotations
  file into a PASS-correctness/verification-yield/cost report, plus a
  small seed question-and-annotation set under `examples/eval/` for
  running it.
- An `openai-deep` adapter (OpenAI Deep Research, `o4-mini-deep-research`,
  Responses API background mode): landed fixtures-first, then enabled the
  same day after one live adoption occurrence (RFC 9110 lookup, terminal
  success on the second poll, 4 citations, ~30k tokens) satisfied the same
  gate perplexity crossed. The deep line now has two independent vendors.

### Changed

- `synthesis` posture now shares the Medium/High coverage-audit gate with
  `scientific`/`decision`: its posture promise is itself a coverage/
  omissions declaration, so a `synthesis` PASS at those tiers requires a
  completed, dispositioned coverage-audit verification record. It still
  has no anti-lock-in requirement of its own.
- `HARNESS.md`'s anti-lock-in reinforcement step now states explicitly
  that every finding must be dispositioned (refuted, absorbed into a
  revised candidate, or recorded as an open tension with a revisit
  trigger) -- noting counter-evidence without resolving it does not
  satisfy the step.
- The README CLI section lists all 22 `deep-research-state` subcommands.

### Fixed

- `promote_provider_payload` now refuses providers whose
  `action_categories` include `"deep"`: an async deep job's result is
  spooled under `provider_spool/<poll_action_id>.raw.json`, not under the
  submitted action_id recorded on the retrieval occurrence, so promoting
  by that action_id would have ingested the submit-accept stub instead of
  the actual result.
- `scripts/calibration_report.py`'s cost extraction now also reads exa's
  `costDollars.total` and openalex's `meta.cost_usd` raw shapes; it
  previously only summed the perplexity_deep/sonar `usage.cost.total_cost`
  shape and silently undercounted sessions that used the other two
  providers.
- Validation's `provider_payload` evidence-lineage branch
  (`artifact.provenance` / `evidence.provider_claims_forbidden` /
  `artifact.storage_rights`) is reachable through the public CLI for the
  first time since 0785603: before the `promote` subcommand existed, no
  public path could create a `provider_payload`-origin artifact, so that
  branch was exercised only by hand-built test fixtures.

## 2.0.0b3

### Added

- An `attempt` CLI subcommand that journals attempt-status transitions
  (`attempted`/`accepted`/`failed`/`uncertain`/`completed`) for actions no
  request boundary executes — host, local, and organizer-pass actions.
  Illegal transitions are rejected by the existing quota transition table.

### Removed

- The legacy worker CLI (`scripts/deep_research.py`, `WORKERS.md`) and its
  `gemini` optional dependency.
- The credential doctor (`scripts/doctor.py`, `deep-research-doctor`).
- The pre-v2 state validator (`scripts/validate_state.py`).
- Golden transcript validation (`scripts/validate_transcripts.py`,
  `examples/transcripts/`) and the legacy-worker quickstart samples
  (`examples/quickstart/`).
- Seven unbound registry candidates with no adapter binding: `cascade`,
  `openai`, `gemini`, `deepseek`, `mojeek`, `jina`, `firecrawl`.
- Unused harness code: the `ingest_provider_artifact` ingestion path, the
  session-locked `record_attempt_status` wrapper, the `render_session` thin
  wrapper, the unreachable `"interrupted"` attempt status, and the dead
  `evidence_capabilities.requires_direct_fetch` registry field.

### Changed

- Documentation (`SKILL.md`, `HARNESS.md`, `AGENTS.md`, `SCENARIOS.md`, both
  READMEs) now states the resolved provider registry as the sole source of
  truth for route readiness, replacing references to the credential doctor
  and the legacy worker CLI.
- The README CLI section lists all 20 `deep-research-state` subcommands.
- `.env.example` drops keys with no consuming code (`OPENAI_API_KEY`,
  `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`) and describes Exa as enabled rather
  than pending benchmark.

### Fixed

- High-tier `PASS` was unreachable through the CLI surface: validation
  requires the context-separated verifier's organizer-pass action to reach
  attempt status `completed`, but no command could journal attempt status
  for such actions (only boundary-executed routes journal their own). The
  new `attempt` subcommand closes the gap; `HARNESS.md` documents the step.
- The redaction-review and fetched-source ingestion errors now name the
  exact CLI flags and patch step that satisfy them.
- `attempt` refuses boundary-managed categories (probe/deep/processor/
  transport): journaling "attempted" on such a permit would permanently
  void it, since the boundary refuses already-attempted actions.
- Validation now independently re-derives every action's attempt lifecycle
  (`attempt.unknown_action`/`attempt.from_status`/`attempt.transition`)
  instead of trusting writer-side enforcement of the transition table.
- The b2 entry below describing the release gate as "one-command
  no-network" is inaccurate: the gate's dependency-audit step (`pip_audit`)
  requires network access. Left as originally written since changelog
  history is not rewritten; noted here instead.
