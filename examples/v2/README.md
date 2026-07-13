# V2 Runtime Example

`medium-contract.json` is an intentional evidence-shortfall fixture: `init`
succeeds, `validate` exits `2`, and `render` still delivers a blocked package.
It authorizes:

- one host-native primary scout request;
- one local applicability action;
- one reserved host-native anti-lock-in request;
- one reserved host-native verification request;
- one Organizer final review pass;
- zero external provider, processor, experiment, or transport requests.

Fixture confirmation hashes only bind the smoke-test contract. A real `/deep` session follows the canonical `SKILL.md` seven-line card; after the user chooses a tier, the internal bridge handles binding without showing hashes or requiring a second confirmation.

```bash
set -e
ROOT="$(pwd)"
CLI="$ROOT/.venv/bin/deep-research-state"
SESSION="$(mktemp -d)/session"

"$CLI" init "$SESSION" \
  --contract "$ROOT/examples/v2/medium-contract.json" \
  --json

VALIDATE_EXIT=0
"$CLI" validate "$SESSION" --json || VALIDATE_EXIT=$?
test "$VALIDATE_EXIT" -eq 2
"$CLI" render "$SESSION" --json
```

The CLI records permits and state transitions; it does not itself perform host-native WebSearch. External providers remain disabled until their adapters use the common v2 request boundary and pass adoption gates.
