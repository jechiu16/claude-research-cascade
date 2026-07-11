# Security policy

## Reporting a vulnerability

Do not open a public issue for credential exposure, request-boundary bypass,
artifact disclosure, or integrity failures. Use GitHub's private vulnerability
reporting for this repository.

Include the affected version, a minimal reproduction, expected invariant, and
whether any external provider request or user artifact was involved. Remove all
real credentials and private data from the report.

## Supported versions

Security fixes target the latest published beta and the default branch while
the V2 runtime remains in beta.

## Credential handling

- Store provider keys only in process environment variables or an ignored
  `.env` file.
- Treat any key pasted into chat, logs, fixtures, issues, or commits as exposed
  and rotate it immediately.
- Presence of a key never enables a provider route by itself.

The runtime rejects known secret patterns during artifact ingestion, but this
is a deterministic safety floor rather than a complete data-loss-prevention
system. Read [HARNESS.md](HARNESS.md) for the full threat model and boundaries.
