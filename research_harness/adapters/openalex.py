"""openalex adapter: OpenAlex works search, sync scholarly paper listing."""

from __future__ import annotations

import json
import urllib.parse
from typing import Optional

from ..boundary import AdapterParseError, BoundaryError, ParsedResult, RequestSpec

BASE_URL = "https://api.openalex.org/works"
PER_PAGE = 20
SELECT_FIELDS = (
    "id,doi,display_name,publication_year,publication_date,cited_by_count,"
    "is_retracted,primary_location"
)


def build(query: str, env: dict[str, str]) -> RequestSpec:
    key = env.get("OPENALEX_API_KEY")
    if not key:
        raise BoundaryError("OPENALEX_API_KEY is not set")
    public_params = {
        "search": query,
        "per_page": PER_PAGE,
        "select": SELECT_FIELDS,
    }
    params = {**public_params, "api_key": key}
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    return RequestSpec(
        method="GET",
        url=url,
        headers={"User-Agent": "research-harness-v2"},
        body=b"",
        timeout_s=30.0,
        fingerprint_url=f"{BASE_URL}?{urllib.parse.urlencode(public_params)}",
    )


def _citation_url(work: dict) -> Optional[str]:
    doi = work.get("doi")
    if isinstance(doi, str) and doi:
        return doi
    primary_location = work.get("primary_location")
    landing_page_url = (
        primary_location.get("landing_page_url") if isinstance(primary_location, dict) else None
    )
    if isinstance(landing_page_url, str) and landing_page_url:
        return landing_page_url
    work_id = work.get("id")
    return work_id if isinstance(work_id, str) and work_id else None


def parse(payload: bytes) -> ParsedResult:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterParseError(f"openalex payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterParseError("openalex payload is not a JSON object")
    works = data.get("results")
    if not isinstance(works, list):
        raise AdapterParseError("openalex payload has no results list")

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    total = meta.get("count")
    raw_cost = meta.get("cost_usd")
    cost = round(raw_cost, 6) if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool) else None

    lines = []
    citations = []
    for work in works:
        if not isinstance(work, dict):
            continue
        title = work.get("display_name") if isinstance(work.get("display_name"), str) else "(untitled)"
        year = work.get("publication_year")
        cited_by_count = work.get("cited_by_count") if isinstance(work.get("cited_by_count"), int) else 0
        retracted = " [RETRACTED]" if work.get("is_retracted") is True else ""
        lines.append(
            f"{title} ({year if year is not None else '?'}){retracted} "
            f"— cited_by_count: {cited_by_count}"
        )
        citation_url = _citation_url(work)
        if citation_url is not None:
            citations.append(
                {
                    "url": citation_url,
                    "title": title,
                    "date": str(year) if year is not None else None,
                }
            )

    return ParsedResult(
        synthesis_text="\n".join(lines),
        citations=citations,
        cost_usd=cost,
        usage={"total_results": total, "returned": len(works)},
        model="openalex/works-search",
        kind="paper_listing",
    )
