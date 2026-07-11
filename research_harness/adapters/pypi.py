"""pypi adapter: PyPI package JSON record fetch (source of record).

Query is a package name. GET /pypi/{name}/json on pypi.org; the JSON body's
``info`` object IS the canonical package record (no synthesis, no
aggregation) — same record-fetch shape as github, so
``evidence_capabilities.can_support_claims`` is true for this route.
"""

from __future__ import annotations

import json
import re

from ..boundary import AdapterParseError, BoundaryError, ParsedResult, RequestSpec

# Mirrors PyPI's own package-name validation (PEP 508 normalization rule):
# starts and ends with an alphanumeric, "._-" allowed in between.
_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")


def build(query: str, env: dict[str, str]) -> RequestSpec:
    # pypi.org/pypi/<name>/json is keyless: no credential is ever attached,
    # so `env` is accepted only to satisfy the shared adapter signature.
    del env
    if not _NAME_RE.fullmatch(query):
        raise BoundaryError(f"pypi query must be a valid package name, got: {query!r}")
    return RequestSpec(
        method="GET",
        url=f"https://pypi.org/pypi/{query}/json",
        headers={
            "Accept": "application/json",
            "User-Agent": "research-harness-v2",
        },
        body=b"",
        timeout_s=30.0,
    )


_RENDER_FIELDS = ("name", "version", "summary", "license", "requires_python", "release_count")


def parse(payload: bytes) -> ParsedResult:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterParseError(f"pypi payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterParseError("pypi payload is not a JSON object")

    info = data.get("info")
    if not isinstance(info, dict):
        raise AdapterParseError("pypi payload has no info object")
    name = info.get("name")
    version = info.get("version")
    if not isinstance(name, str) or not name:
        raise AdapterParseError("pypi payload has no info.name")
    if not isinstance(version, str) or not version:
        raise AdapterParseError("pypi payload has no info.version")

    releases = data.get("releases")
    release_count = len(releases) if isinstance(releases, dict) else None

    # Deterministic compact rendering: fixed field order, one per line,
    # missing/null values render as an empty string so line count and order
    # never shift between packages (matches github's _RENDER_FIELDS pattern).
    values = {
        "name": name,
        "version": version,
        "summary": info.get("summary"),
        "license": info.get("license"),
        "requires_python": info.get("requires_python"),
        "release_count": release_count,
    }
    lines = [f"{key}: {'' if values[key] is None else values[key]}" for key in _RENDER_FIELDS]
    synthesis_text = "\n".join(lines)

    package_url = info.get("package_url")
    citation_url = (
        package_url if isinstance(package_url, str) and package_url
        else f"https://pypi.org/project/{name}/"
    )
    citations = [{"url": citation_url, "title": f"{name} {version}", "date": None}]

    return ParsedResult(
        synthesis_text=synthesis_text,
        citations=citations,
        cost_usd=None,
        usage={},
        model="pypi-json/v1",
        kind="record_fetch",
    )
