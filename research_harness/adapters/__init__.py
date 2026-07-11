"""Adapter registry: one module per provider, registered here.

Keys are exactly "<adapter>@<adapter_version>" as bound by the capability
registry. Each module exposes two pure functions:

    build(query, env) -> RequestSpec   # no network, no side effects
    parse(payload)    -> ParsedResult  # raises AdapterParseError on mismatch

Keep every adapter stdlib-only. Credentials come in through ``env`` and must
never appear in fixtures, occurrences, or fingerprints.
"""

from __future__ import annotations

from . import github, pypi, scholar, sonar

ADAPTERS = {
    "perplexity-chat-completions@v1": {"build": sonar.build, "parse": sonar.parse},
    "github-repos-record@v1": {"build": github.build, "parse": github.parse},
    "semantic-scholar-graph-search@v1": {"build": scholar.build, "parse": scholar.parse},
    "pypi-package-record@v1": {"build": pypi.build, "parse": pypi.parse},
}
