# V2 Runtime Example

`medium-contract.json` is a deterministic, no-paid-provider foundation fixture. It authorizes:

- one host-native primary scout request;
- one local applicability action;
- one reserved host-native anti-lock-in request;
- one reserved host-native verification request;
- one Organizer final review pass;
- zero external provider, processor, experiment, or transport requests.

The confirmation hashes bind this exact card to the committed provider registry. Use it for smoke tests only. For a real session, run `prepare`, show the returned card and three hashes to the user, and call `confirm` only after the user explicitly chooses it.

```bash
PY=/Users/jechiu/dev/parallax/.venv/bin/python
SESSION="$(mktemp -d)/session"

"$PY" scripts/research_state.py init "$SESSION" \
  --question "Choose a cache" \
  --contract examples/v2/medium-contract.json \
  --json

"$PY" scripts/research_state.py validate "$SESSION" --json
"$PY" scripts/research_state.py render "$SESSION" --json
```

The CLI records permits and state transitions; it does not itself perform host-native WebSearch. External providers remain disabled until their adapters use the common v2 request boundary and pass adoption gates.
