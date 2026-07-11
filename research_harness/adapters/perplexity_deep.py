"""perplexity_deep adapter: Perplexity sonar-deep-research, async submit/poll/extract.

Verified against https://docs.perplexity.ai/api-reference/async-sonar-api-request-get.md
(fetched 2026-07-11): POST /v1/async/sonar accepts {"request": {...}} and
returns {"id", "status", ...}; GET /v1/async/sonar/{id} returns the same
shape with "status" in {CREATED, IN_PROGRESS, COMPLETED, FAILED} and, once
COMPLETED, a nested "response" object shaped like a normal chat-completions
body (choices/usage/citations/search_results) — confirmed against the sync
sonar.py adapter's real recorded fixture and the legacy scripts/deep_research.py
prior art, both of which nest cost under response.usage.cost.total_cost.
"""

from __future__ import annotations

import json

from ..boundary import (
    AdapterParseError,
    AdapterTerminalFailure,
    BoundaryError,
    ParsedResult,
    RequestSpec,
)

ASYNC_BASE = "https://api.perplexity.ai/v1/async/sonar"
MODEL = "sonar-deep-research"


def _require_key(env: dict[str, str]) -> str:
    key = env.get("PERPLEXITY_API_KEY")
    if not key:
        raise BoundaryError("PERPLEXITY_API_KEY is not set")
    return key


def submit(query: str, env: dict[str, str]) -> RequestSpec:
    key = _require_key(env)
    body = json.dumps(
        {
            "request": {
                "model": MODEL,
                "messages": [{"role": "user", "content": query}],
                "reasoning_effort": "low",
            }
        }
    ).encode("utf-8")
    return RequestSpec(
        method="POST",
        url=ASYNC_BASE,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        body=body,
        timeout_s=60.0,
    )


def job_token(payload: bytes) -> str:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterParseError(f"perplexity accept payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterParseError("perplexity accept payload is not an object")
    token = data.get("id")
    if not isinstance(token, str) or not token:
        raise AdapterParseError("perplexity accept payload has no id")
    return token


def poll(token: str, env: dict[str, str]) -> RequestSpec:
    key = _require_key(env)
    return RequestSpec(
        method="GET",
        url=f"{ASYNC_BASE}/{token}",
        headers={"Authorization": f"Bearer {key}"},
        body=b"",
        timeout_s=30.0,
    )


def extract(payload: bytes) -> ParsedResult | None:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterParseError(f"perplexity poll payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterParseError("perplexity poll payload is not an object")

    status = data.get("status")
    if not isinstance(status, str) or not status:
        raise AdapterParseError("perplexity poll payload has no status")
    if status == "FAILED":
        raise AdapterTerminalFailure(data.get("error_message") or "perplexity deep job failed")
    if status != "COMPLETED":
        return None  # CREATED / IN_PROGRESS / any other non-terminal status

    response = data.get("response")
    if not isinstance(response, dict):
        raise AdapterParseError("perplexity completed payload has no response")
    try:
        text = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AdapterParseError("perplexity completed payload has no message content") from exc
    if not isinstance(text, str) or not text.strip():
        raise AdapterParseError("perplexity completed message content is empty")

    raw_citations = response.get("search_results") or [
        {"url": url} for url in (response.get("citations") or [])
    ]
    citations = [
        {"url": item.get("url"), "title": item.get("title"), "date": item.get("date")}
        for item in raw_citations
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    ]
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    cost = (usage.get("cost") or {}).get("total_cost") if isinstance(usage.get("cost"), dict) else None
    return ParsedResult(
        synthesis_text=text,
        citations=citations,
        cost_usd=round(cost, 4) if isinstance(cost, (int, float)) else None,
        usage=usage,
        model=MODEL,
        kind="search_synthesis",
    )
