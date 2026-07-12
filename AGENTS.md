# Agent Deep Research Trigger — Codex Binding

Use this protocol only when the user explicitly invokes `/deep`. You are the **Organizer** of the host-neutral v2 runtime in [HARNESS.md](HARNESS.md), not a single model producing a long research answer from memory.

## Discovery

Codex loads `AGENTS.md` from the project hierarchy. Set
`AGENT_DEEP_RESEARCH_DIR` to this checkout or install the skill under
`~/.agents/skills/deep`, then invoke the runtime with the project venv:

```bash
"$PY" "$AGENT_DEEP_RESEARCH_DIR/scripts/research_state.py" --help
```

## Required Protocol

1. Classify the question by `posture`: `lookup`, `synthesis`, `scientific`, or `decision`.
2. Recommend `tier=low|medium|high|custom`. Show exact logical invocations and physical request counts, including reserved reinforcement calls. The user chooses before any research action.
3. Run `prepare`, display the card and binding hashes, and wait. Only after explicit confirmation may you run `confirm` and `init`.
4. Use exactly one primary scout route. Acquire the exact stage permit before every host, local, or future external action.
5. Store semantic truth only in canonical `state.json`. Apply revision-checked patches and provenance-gated artifact ingestion; do not maintain a competing Markdown report.
6. Use anti-lock-in and coverage audit for Medium/High scientific or decision work. High `PASS` requires context-separated verification.
7. Run `validate` and `render` before delivery. Never report `PASS` when validation is false.

## Current Execution Boundary

The external routes enabled at any time are exactly those the resolved provider registry marks enabled and v2-bound (`research_state.py execute` after a permit) — inspect them with `providers --json`. Exa is reserved for anti-lock-in or verification where its independent index adds value; Brave is the recommended general scout. Every other external provider and processor route stays disabled until its worker adapter passes the same gates. A present credential is not execution readiness. No disabled route may be exercised through any side channel.

First-run sanity check: `"$PY" "$AGENT_DEEP_RESEARCH_DIR/scripts/research_state.py" demo /tmp/deep-demo --json` proves the whole runtime (permit -> occurrence -> validate -> render) with zero network and zero cost.

## Codex Map

| Harness operation | Codex binding |
|---|---|
| User contract | Plain chat options with counts, cost uncertainty, risk, and recommendation |
| Host retrieval | Native web tools after the matching host permit |
| Local applicability | Shell/file inspection after a local permit, with network egress disabled |
| Runtime | `scripts/research_state.py` using an absolute checkout path |
| Recovery | `recover` resumes WAL and already-authorized pending purge only |
| Delivery gate | `validate`; if true, `render` the hash-bound HTML |
| Continuing development | Hand off decision, claims, disputes, safe reversible actions, acceptance tests, and flip conditions |

When the user's working language is Traditional Chinese, author human-facing canonical narrative fields in Traditional Chinese before validation and rendering. Preserve exact evidence excerpts, source titles, identifiers, URLs, hashes, provider IDs, status tokens, and machine diagnostics in their original form. The deterministic renderer does not call a translation model.

All JSON commands write exactly one object on stdout with `--json`; errors and progress belong on stderr. Keep raw local/user material private unless the user explicitly authorizes external egress after the relevant adapter exists.
