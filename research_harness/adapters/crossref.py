"""crossref adapter: Crossref works search, sync scholarly paper listing.

Query is a free-text keyword phrase. GET /works on api.crossref.org, scored
relevance search over the works index (not a direct DOI-record fetch), so
this is a paper_listing shape like scholar's, not a record_fetch shape like
github's. The route is keyless: the "mailto" query param is an email address
that opts the request into Crossref's polite pool (higher priority, less
throttling than the anonymous public pool) -- it is not a credential, so
required_env stays empty and env is accepted only for adapter-protocol parity
with sonar/github/scholar.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Optional

from ..boundary import AdapterParseError, ParsedResult, RequestSpec

BASE_URL = "https://api.crossref.org/works"
MAILTO = "samuel7014@gmail.com"
ROWS = 20


def build(query: str, env: dict[str, str]) -> RequestSpec:
    del env  # keyless route; nothing to read from the environment
    params = {"query": query, "rows": ROWS, "mailto": MAILTO}
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    return RequestSpec(
        method="GET",
        url=url,
        headers={"User-Agent": f"research-harness-v2 (mailto:{MAILTO})"},
        body=b"",
        timeout_s=30.0,
    )


def _issued_year(issued: object) -> Optional[int]:
    # issued["date-parts"] is [[year, month, day]] with trailing parts
    # optional -- and, seen live on records missing a publication date (e.g.
    # some dissertations), the year itself can be [[None]].
    if not isinstance(issued, dict):
        return None
    date_parts = issued.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts:
        return None
    first = date_parts[0]
    if not isinstance(first, list) or not first:
        return None
    year = first[0]
    return year if isinstance(year, int) else None


def parse(payload: bytes) -> ParsedResult:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterParseError(f"crossref payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterParseError("crossref payload is not a JSON object")
    message = data.get("message")
    if not isinstance(message, dict):
        raise AdapterParseError("crossref payload has no message object")
    items = message.get("items")
    if not isinstance(items, list):
        raise AdapterParseError("crossref payload has no message.items list")

    total = message.get("total-results")
    lines = [
        f"Crossref works search: {len(items)} of "
        f"{total if isinstance(total, int) else '?'} results\n"
    ]
    citations = []
    for item in items:
        if not isinstance(item, dict):
            continue
        titles = item.get("title")
        title = (
            titles[0]
            if isinstance(titles, list) and titles and isinstance(titles[0], str)
            else None
        )
        doi_raw = item.get("DOI")
        doi = doi_raw if isinstance(doi_raw, str) and doi_raw else None
        year = _issued_year(item.get("issued"))
        ref_count = item.get("is-referenced-by-count")
        ref_count = ref_count if isinstance(ref_count, int) else 0

        display_title = title or doi or "(untitled)"
        lines.append(
            f"\n- {display_title} ({year if year is not None else '?'}) "
            f"— cited by: {ref_count}"
        )
        citations.append(
            {
                "url": f"https://doi.org/{doi}" if doi else None,
                "title": title or doi,
                "date": str(year) if year is not None else None,
            }
        )

    return ParsedResult(
        synthesis_text="".join(lines),
        citations=citations,
        cost_usd=None,
        usage={"total_results": total, "returned": len(items)},
        model="crossref/works-search",
        kind="paper_listing",
    )
