"""Adapter registry: one module per provider, registered here.

Keys are exactly "<adapter>@<adapter_version>" as bound by the capability
registry. Sync adapters (registry transport.mode "sync") expose two pure
functions:

    build(query, env) -> RequestSpec   # no network, no side effects
    parse(payload)    -> ParsedResult  # raises AdapterParseError on mismatch

Async adapters (registry transport.mode "async") expose four:

    submit(query, env)  -> RequestSpec         # the paid POST; never retried
    job_token(payload)  -> str                 # bare provider-native id from the accept body
    poll(token, env)    -> RequestSpec         # one status GET
    extract(payload)    -> ParsedResult | None # None = still running;
                                                # raises AdapterParseError on
                                                # malformed-terminal, or
                                                # AdapterTerminalFailure on a
                                                # well-formed provider failure

Keep every adapter stdlib-only. Credentials come in through ``env`` and must
never appear in fixtures, occurrences, or fingerprints.
"""

from __future__ import annotations

from . import github, perplexity_deep, pypi, scholar, sonar

ADAPTERS = {
    "perplexity-chat-completions@v1": {"build": sonar.build, "parse": sonar.parse},
    "github-repos-record@v1": {"build": github.build, "parse": github.parse},
    "semantic-scholar-graph-search@v1": {"build": scholar.build, "parse": scholar.parse},
    "pypi-package-record@v1": {"build": pypi.build, "parse": pypi.parse},
    "perplexity-async-sonar@v1": {
        "submit": perplexity_deep.submit,
        "job_token": perplexity_deep.job_token,
        "poll": perplexity_deep.poll,
        "extract": perplexity_deep.extract,
    },
}
