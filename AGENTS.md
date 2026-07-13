# Agent Deep Research Trigger - Codex Binding

Use this binding only when the user explicitly invokes `/deep`. The complete
shared public protocol lives in [SKILL.md](SKILL.md); do not create a second
Codex-specific flow.

Codex is the host Organizer and conclusion author. Show one confirmation card
with `light`, `standard`, and `heavy` count vectors, then run the selected work
in the background. Provider reports buy discovery breadth, not truth. After
each report, Codex selects targeted re-verification, corrects or annotates the
result, and always delivers canonical JSON plus Traditional Chinese HTML.

[HARNESS.md](HARNESS.md) is an internal runtime bridge, not a second public
protocol. Read it only after profile confirmation. Use the repo-local CLI and
its registry, cost-class quota, evidence, validation, and rendering machinery;
do not reimplement those capabilities in prompt text.
