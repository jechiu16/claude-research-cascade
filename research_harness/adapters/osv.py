"""osv adapter: OSV.dev vulnerability query, sync record fetch (source of record).

Query is "<ecosystem>/<package>", split on the FIRST slash only: the package
half may itself contain a slash (e.g. npm's scoped "@angular/core"), so this
cannot reuse github's stricter exactly-one-slash regex. POST /v1/query on
api.osv.dev; the JSON body IS the canonical vulnerability record for that
package (no synthesis, no aggregation) — same record-fetch shape as
github/pypi, so ``evidence_capabilities.can_support_claims`` is true for
this route. Unlike github/pypi's bodyless GET, this is a POST with a JSON
body — same transport shape as sonar's paid synthesis call, but keyless and
a direct source-of-record fetch instead.
"""

from __future__ import annotations

import json

from ..boundary import AdapterParseError, BoundaryError, ParsedResult, RequestSpec

QUERY_URL = "https://api.osv.dev/v1/query"
SUMMARY_EXCERPT_LIMIT = 120


def build(query: str, env: dict[str, str]) -> RequestSpec:
    # api.osv.dev is keyless: no credential is ever attached, so `env` is
    # accepted only to satisfy the shared adapter signature.
    del env
    ecosystem, sep, name = query.partition("/")
    if not sep or not ecosystem or not name:
        raise BoundaryError(f'osv query must be "<ecosystem>/<package>", got: {query!r}')
    body = json.dumps({"package": {"ecosystem": ecosystem, "name": name}}).encode("utf-8")
    return RequestSpec(
        method="POST",
        url=QUERY_URL,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "research-harness-v2",
        },
        body=body,
        timeout_s=30.0,
    )


def parse(payload: bytes) -> ParsedResult:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterParseError(f"osv payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterParseError("osv payload is not a JSON object")

    # OSV's own shape for "no known vulnerabilities" is a bare {} — a
    # complete, valid no-hits record, not a parse failure. Only a
    # present-but-wrong-typed "vulns" is a contract violation.
    vulns = data.get("vulns", [])
    if not isinstance(vulns, list):
        raise AdapterParseError("osv payload 'vulns' is not a list")

    lines: list[str] = []
    citations: list[dict[str, object]] = []
    for vuln in vulns:
        if not isinstance(vuln, dict):
            continue
        vuln_id = vuln.get("id")
        summary = vuln.get("summary") if isinstance(vuln.get("summary"), str) else None
        modified = vuln.get("modified")
        excerpt = summary[:SUMMARY_EXCERPT_LIMIT] if summary else ""

        # A record without a string id has no resolvable URL — drop the
        # citation (repo convention) instead of fabricating .../None.
        if isinstance(vuln_id, str) and vuln_id:
            citations.append(
                {
                    "url": f"https://osv.dev/vulnerability/{vuln_id}",
                    "title": f"{vuln_id}: {summary}" if summary else vuln_id,
                    "date": modified,
                }
            )
        parts = [str(vuln_id)]
        if excerpt:
            parts.append(excerpt)
        parts.append(f"modified {modified}")
        lines.append(" — ".join(parts))

    synthesis_text = "\n".join(lines) if lines else "no known vulnerabilities recorded"

    return ParsedResult(
        synthesis_text=synthesis_text,
        citations=citations,
        cost_usd=None,
        usage={"vuln_count": len(vulns)},
        model="osv-query/v1",
        kind="record_fetch",
    )
