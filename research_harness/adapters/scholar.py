"""scholar adapter: Semantic Scholar Graph API paper search, sync paper listing."""

from __future__ import annotations

import json
import urllib.parse

from ..boundary import AdapterParseError, ParsedResult, RequestSpec

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,abstract,citationCount,authors,url,openAccessPdf,tldr"
LIMIT = 20
EXCERPT_LIMIT = 200


def build(query: str, env: dict[str, str]) -> RequestSpec:
    # Keyless shared pool by default; an S2_API_KEY raises rate limits but is
    # never required, per api.semanticscholar.org/api-docs/.
    params = {"query": query, "limit": LIMIT, "fields": FIELDS}
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    headers: dict[str, str] = {}
    key = env.get("S2_API_KEY")
    if key:
        headers["x-api-key"] = key
    return RequestSpec(
        method="GET",
        url=url,
        headers=headers,
        body=b"",
        timeout_s=30.0,
    )


def _excerpt(paper: dict) -> str:
    tldr = paper.get("tldr")
    text = tldr.get("text") if isinstance(tldr, dict) else None
    if not isinstance(text, str) or not text.strip():
        text = paper.get("abstract")
    return text[:EXCERPT_LIMIT] if isinstance(text, str) else ""


def parse(payload: bytes) -> ParsedResult:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterParseError(f"scholar payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterParseError("scholar payload is not a JSON object")
    papers = data.get("data")
    if not isinstance(papers, list):
        raise AdapterParseError("scholar payload has no data list")

    total = data.get("total")
    lines = [
        f"Semantic Scholar paper search: {len(papers)} of "
        f"{total if isinstance(total, int) else '?'} results (by relevance)\n"
    ]
    citations = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        title = paper.get("title") if isinstance(paper.get("title"), str) else "(untitled)"
        year = paper.get("year")
        citation_count = paper.get("citationCount") if isinstance(paper.get("citationCount"), int) else 0
        lines.append(
            f"\n- {title} ({year if year is not None else '?'}) "
            f"— citations: {citation_count}"
        )
        excerpt = _excerpt(paper)
        if excerpt:
            lines.append(f"\n  {excerpt}")
        citations.append(
            {
                "url": paper.get("url") if isinstance(paper.get("url"), str) else None,
                "title": title,
                "date": str(year) if year is not None else None,
            }
        )

    return ParsedResult(
        synthesis_text="".join(lines),
        citations=citations,
        cost_usd=None,
        usage={"total_results": total, "returned": len(papers)},
        model="s2-graph/paper-search",
        kind="paper_listing",
    )
