---
scenario: quick-fact
preset: fast
contract: depth=shallow | independence=single | strictness=first
state: skipped-single-action
verification: completed
---

# Golden Transcript: Quick Fact Check

This transcript calibrates a cheap `/deep` run. It shows that even a shallow answer still asks the three-axis contract, records evidence status, performs a verification-floor check when cheap, and includes spend/artifacts.

## Transcript

**User:** `/deep What license does this repository use?`

**Organizer:** I infer the target from context: identify the repository license for `agent-deep-research-trigger`. No framing question needed; the answer is local and source-of-record.

Before spending, choose the three-axis research contract:

| Preset | Depth | Independence | Strictness | Tradeoff |
|---|---|---|---|---|
| `fast` (Recommended) | shallow | single | first | One source-of-record check plus cheap verification. |
| `standard` | medium | two-source | gaps | Use if you need a broader licensing/compliance read. |
| `decision` | deep | cross-family-blind | chase | Overkill unless this affects legal/commercial distribution. |

**User:** Use `fast`.

**Organizer:** Contract confirmed: `depth=shallow | independence=single | strictness=first`.

Research State: skipped because this is a shallow single-action source-of-record lookup. Ledger: not required. Spend target: $0.00.

## Actions

Batch 1:

- `host-fetch`: read `LICENSE`
- `host-fetch`: spot-check README license link

Reason: local source-of-record evidence is cheaper and stronger than an external model answer.

## Evidence Status

| id | claim | status | sources | independence |
|---|---|---|---|---|
| C1 | The repository uses the MIT License. | corroborated | `LICENSE`; README license link | local source-of-record |

## Reconciliation

No conflict. The `LICENSE` file and README license link point to the same license family.

## Verification

Verification floor completed:

- Checked `LICENSE` directly.
- Checked README license link points to `LICENSE`.

No discrepancy found.

## Delivery

Executive answer: the repository uses the **MIT License**.

Research contract: `depth=shallow | independence=single | strictness=first`; framing assumption: answer only the license of this repository, not downstream dependency licenses.

Key finding:

- `C1` MIT License: `corroborated` by local source-of-record files.

Load-bearing claim: if `LICENSE` were changed or removed, the conclusion would change.

Spend and artifacts:

- Spend: `$0.00`
- State file: skipped (`fast` single-action run)
- Ledger: not required
- Artifacts: `LICENSE`, README license link

Recommendation: treat the repository as MIT-licensed, while checking dependency licenses separately if the question is redistribution/compliance.

Handoff: if another Agent resumes, inspect `LICENSE` first, then dependency manifests if the scope expands beyond repository license.
