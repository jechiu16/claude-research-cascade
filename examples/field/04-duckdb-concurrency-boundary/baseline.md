# Host Baseline: DuckDB Concurrency Boundary

- Captured: 2026-07-14 before D1 or external search
- Basis: Codex parameterized knowledge plus the question's stated Parallax context
- Evidence status: unverified; this is not a canonical research conclusion

## Baseline Decision

Parallax should keep one process as the exclusive DuckDB writer and migration
owner. Work inside that process may use separate connections or cursors, but
independent processes should not coordinate concurrent writes to the same
database file. CLI and report consumers should use an immutable export,
snapshot, or an owner-mediated interface instead of assuming that a read-only
open is safe while the writer is active.

## Baseline Acceptance Boundary

1. Two same-process connections attempt non-conflicting appends and conflicting
   updates; conflicts must be surfaced rather than silently lost.
2. A second process attempts a write while the owner is active; it must fail
   promptly with an operator-visible result and must not corrupt the database.
3. A reporting process attempts a read while the owner is active; the supported
   path must be explicit, deterministic, and covered rather than inferred from
   one successful run.
4. A writer is terminated inside a transaction; restart must show atomic
   commit/rollback behavior and an intelligible recovery result.
5. Schema migration and maintenance operations run only under exclusive owner
   control.

## Uncertainties To Verify

- DuckDB's current documented boundary for multi-process read-only access while
  another process holds a read-write connection.
- Whether same-process optimistic concurrency treats append-only and update
  conflicts differently in the versions Parallax supports.
- Any filesystem or deployment constraints that make lock behavior unsafe.
- Whether official guidance recommends application-level retry, serialization,
  or an alternate service boundary for multi-process writes.

## Baseline Flip Condition

Change this decision only if current official DuckDB documentation supports a
broader multi-process pattern that matches Parallax's deployment and can be
covered by deterministic failure-path tests.
