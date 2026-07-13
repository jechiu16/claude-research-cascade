"""Shared canonical-form primitives.

Every hash binding in the runtime (contract cards, registry snapshots, state
revisions, event chains, artifact policies) depends on one exact byte form.
That byte form lives here and nowhere else — a second copy is a drift risk,
not a convenience.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit


RETENTION_RANK = {"forbidden": 0, "ephemeral": 1, "session": 2, "persistent": 3}


def canonical_question(value: Any) -> str:
    """Canonicalize a user question without changing its internal layout."""

    if not isinstance(value, str):
        raise ValueError("question must be a string")
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    for character in normalized:
        codepoint = ord(character)
        category = unicodedata.category(character)
        if category == "Cc" and character not in {"\n", "\t"}:
            raise ValueError("question contains a forbidden control character")
        if codepoint in {0x200B, 0xFEFF, 0x2060}:
            raise ValueError("question contains a forbidden zero-width character")
        if 0x202A <= codepoint <= 0x202E or 0x2066 <= codepoint <= 0x2069:
            raise ValueError("question contains a forbidden bidi control")
    normalized = normalized.strip()
    if not normalized or not any(
        not character.isspace() and unicodedata.category(character)[0] not in {"C", "M"}
        for character in normalized
    ):
        raise ValueError("question must not be empty or visual-only")
    return normalized


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    """SHA-256 of the canonical JSON form."""

    return hashlib.sha256(canonical_json(value)).hexdigest()


def is_count(value: Any) -> bool:
    """A non-negative integer count (bool excluded)."""

    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_positive_count(value: Any) -> bool:
    return is_count(value) and value > 0


def indexed(items: Any) -> dict[str, dict[str, Any]]:
    """Index a state section's entries by their string id."""

    if not isinstance(items, list):
        return {}
    return {
        item["id"]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def canonical_source_key(source_url: str) -> str:
    """Return the one safe identity form for an HTTP(S) source URL."""

    if not isinstance(source_url, str) or not source_url or source_url != source_url.strip():
        raise ValueError("source URL must be a non-empty, trimmed string")
    if any(ord(character) < 32 for character in source_url):
        raise ValueError("source URL contains control characters")
    try:
        parsed = urlsplit(source_url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("source URL is malformed") from exc
    if scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ValueError("source URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL must not contain credentials")
    host = hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 80 if scheme == "http" else 443
    netloc = host if port is None or port == default_port else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def normalize_upstream_key(value: str) -> str:
    """Normalize upstream identity once before it enters canonical state."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("upstream key must be a non-empty string")
    cleaned = value.strip()
    if cleaned.casefold() == "unknown":
        return "unknown"
    try:
        parsed = urlsplit(cleaned)
    except ValueError:
        parsed = None
    if parsed is not None and parsed.scheme.lower() in {"http", "https"}:
        return canonical_source_key(cleaned)
    return cleaned.casefold()
