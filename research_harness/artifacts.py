"""Immutable raw artifact ingestion and fail-closed purge recovery."""

from __future__ import annotations

import copy
import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any, Optional

from ._canon import RETENTION_RANK, canonical_source_key, normalize_upstream_key, sha256_hex
from .quota import ACTION_ID_RE
from .storage import (
    _apply_artifact_state_patch_unlocked,
    _fsync_dir,
    _load_state_unlocked,
    _read_events_unlocked,
    _recover_session_unlocked,
    _write_all,
    session_lock,
)


ARTIFACT_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
MEDIA_EXTENSIONS = {
    "application/octet-stream": ".bin",
    "application/json": ".json",
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "text/csv": ".csv",
    "text/html": ".html",
    "text/markdown": ".md",
    "text/plain": ".txt",
}
SENSITIVITIES = frozenset({"public", "internal", "local-sensitive", "secret"})
RETENTIONS = frozenset({"session", "persistent"})
SCANNER_VERSION = "deterministic-secret-floor-v1"
_SECRET_ASSIGNMENT_RE = re.compile(
    rb"(?im)^\s*(?:export\s+)?[A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY)\s*[:=]"
)
_PEM_PRIVATE_KEY_RE = re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
_PROVIDER_PREFIX_RE = re.compile(
    rb"(?i)(?:^|[^A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{8,}|pplx-[A-Za-z0-9_-]{8,}|s2k-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{12,})"
)


class ArtifactPolicyError(RuntimeError):
    """Artifact provenance or policy does not authorize the requested operation."""


class ArtifactExists(ArtifactPolicyError):
    """An immutable artifact ID or destination already exists."""


class SecretDetected(ArtifactPolicyError):
    """The source is secret-classified or matches the deterministic rejection floor."""


def _require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactPolicyError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_common_request(
    artifact_id: str,
    media_type: str,
    sensitivity: str,
    retention: str,
    include_in_html: bool,
    now: str,
    redaction_review: Optional[dict[str, Any]],
) -> tuple[str, bool, Optional[dict[str, Any]]]:
    if not isinstance(artifact_id, str) or ARTIFACT_ID_RE.fullmatch(artifact_id) is None:
        raise ArtifactPolicyError("artifact_id is invalid")
    extension = MEDIA_EXTENSIONS.get(media_type)
    if extension is None:
        raise ArtifactPolicyError("media_type is not allowlisted")
    if sensitivity not in SENSITIVITIES:
        raise ArtifactPolicyError("sensitivity is invalid")
    if sensitivity == "secret":
        raise SecretDetected("secret-classified content cannot be persisted")
    if retention not in RETENTIONS:
        raise ArtifactPolicyError("retention is invalid")
    if not isinstance(include_in_html, bool):
        raise ArtifactPolicyError("include_in_html must be boolean")
    _require_nonempty(now, "now")

    review = copy.deepcopy(redaction_review)
    if sensitivity == "local-sensitive":
        required = ("reviewed_by", "reviewed_at", "method")
        if not isinstance(review, dict) or any(
            not isinstance(review.get(field), str) or not review[field].strip() for field in required
        ):
            raise ArtifactPolicyError(
                "local-sensitive artifacts require a complete redaction review"
                " (pass --reviewed-by, --reviewed-at, --review-method)"
            )
        include_in_html = False
    elif review is not None and not isinstance(review, dict):
        raise ArtifactPolicyError("redaction_review must be an object")
    return extension, include_in_html, review


def _open_regular_source(source_path: Path) -> tuple[int, os.stat_result]:
    source_path = Path(source_path)
    if source_path.name.lower() == ".env" or source_path.name.lower().startswith(".env."):
        raise SecretDetected("environment files cannot be ingested")
    try:
        metadata = source_path.lstat()
    except OSError as exc:
        raise ArtifactPolicyError("source file is not readable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ArtifactPolicyError("source must be a regular non-symlink file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(source_path, flags)
    except OSError as exc:
        raise ArtifactPolicyError("source file could not be opened safely") from exc
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode):
        os.close(fd)
        raise ArtifactPolicyError("opened source is not a regular file")
    return fd, opened


def _contains_secret_marker(data: bytes) -> bool:
    return bool(
        _SECRET_ASSIGNMENT_RE.search(data)
        or _PEM_PRIVATE_KEY_RE.search(data)
        or _PROVIDER_PREFIX_RE.search(data)
    )


def _scan_fd(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    carry = b""
    while True:
        chunk = os.read(fd, 64 * 1024)
        if not chunk:
            break
        window = carry + chunk
        if _contains_secret_marker(window):
            raise SecretDetected("content matches the deterministic secret rejection floor")
        carry = window[-512:]
    os.lseek(fd, 0, os.SEEK_SET)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _reject_managed_source(session_dir: Path, source_path: Path) -> None:
    for managed_name in ("raw", "provider_spool", ".provider-spool"):
        managed = session_dir / managed_name
        if managed.exists() and _is_within(source_path, managed):
            raise ArtifactPolicyError("managed artifact paths cannot be relabelled as local input")


def _ensure_raw_dir(session_dir: Path) -> Path:
    raw_dir = session_dir / "raw"
    if raw_dir.exists():
        if raw_dir.is_symlink() or not raw_dir.is_dir():
            raise ArtifactPolicyError("raw path must be a non-symlink directory")
        if raw_dir.stat().st_mode & 0o077:
            raise ArtifactPolicyError("raw directory permissions are not private")
    else:
        raw_dir.mkdir(mode=0o700)
        _fsync_dir(session_dir)
    return raw_dir


def _raw_bytes_used(raw_dir: Path) -> int:
    total = 0
    for path in raw_dir.iterdir():
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ArtifactPolicyError("raw directory contains a non-regular entry")
        total += metadata.st_size
    return total


def _copy_fd_to_temp(fd: int, temp_path: Path, byte_limit: int) -> tuple[int, str]:
    try:
        out_fd = os.open(temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ArtifactExists("artifact staging path already exists") from exc
    digest = hashlib.sha256()
    byte_count = 0
    carry = b""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > byte_limit:
                raise ArtifactPolicyError("raw storage byte ceiling would be exceeded")
            window = carry + chunk
            if _contains_secret_marker(window):
                raise SecretDetected("content matches the deterministic secret rejection floor")
            carry = window[-512:]
            digest.update(chunk)
            _write_all(out_fd, chunk)
        os.fsync(out_fd)
    except BaseException:
        os.close(out_fd)
        temp_path.unlink(missing_ok=True)
        raise
    os.close(out_fd)
    return byte_count, digest.hexdigest()


def _copy_bytes_to_temp(payload: bytes, temp_path: Path, byte_limit: int) -> tuple[int, str]:
    """Write host-returned bytes without turning them into a local action."""

    if not isinstance(payload, bytes):
        raise ArtifactPolicyError("host capture payload must be bytes")
    if len(payload) > byte_limit:
        raise ArtifactPolicyError("raw storage byte ceiling would be exceeded")
    if _contains_secret_marker(payload):
        raise SecretDetected("content matches the deterministic secret rejection floor")
    try:
        out_fd = os.open(temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ArtifactExists("artifact staging path already exists") from exc
    try:
        _write_all(out_fd, payload)
        os.fsync(out_fd)
    except BaseException:
        os.close(out_fd)
        temp_path.unlink(missing_ok=True)
        raise
    os.close(out_fd)
    return len(payload), hashlib.sha256(payload).hexdigest()


def _ingest_unlocked(
    session_dir: Path,
    source_path: Optional[Path],
    artifact_id: str,
    media_type: str,
    sensitivity: str,
    retention: str,
    include_in_html: bool,
    provenance: dict[str, Any],
    now: str,
    redaction_review: Optional[dict[str, Any]],
    policy_extra: Optional[dict[str, Any]] = None,
    source_bytes: Optional[bytes] = None,
    host_capture: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    extension, include_in_html, review = _validate_common_request(
        artifact_id,
        media_type,
        sensitivity,
        retention,
        include_in_html,
        now,
        redaction_review,
    )
    state = _load_state_unlocked(session_dir)
    if any(item.get("id") == artifact_id for item in state.get("artifact_index", [])):
        raise ArtifactExists(f"artifact {artifact_id} already exists")

    raw_dir = _ensure_raw_dir(session_dir)
    destination = raw_dir / f"{artifact_id}{extension}"
    temp_path = raw_dir / f".{artifact_id}.tmp"
    if destination.exists() or destination.is_symlink() or temp_path.exists() or temp_path.is_symlink():
        raise ArtifactExists(f"artifact storage for {artifact_id} already exists")

    ceiling = state["contract"]["resource_envelope"]["external"]["raw_storage_bytes"]
    if not isinstance(ceiling, int) or isinstance(ceiling, bool) or ceiling < 0:
        raise ArtifactPolicyError("raw storage byte ceiling is invalid")
    remaining = ceiling - _raw_bytes_used(raw_dir)
    if source_bytes is not None:
        byte_count, digest = _copy_bytes_to_temp(source_bytes, temp_path, remaining)
    else:
        if source_path is None:
            raise ArtifactPolicyError("artifact source is required")
        fd, source_metadata = _open_regular_source(source_path)
        try:
            if source_metadata.st_size > remaining:
                raise ArtifactPolicyError("raw storage byte ceiling would be exceeded")
            _scan_fd(fd)
            byte_count, digest = _copy_fd_to_temp(fd, temp_path, remaining)
        finally:
            os.close(fd)

    policy_snapshot = {
        "artifact_policy": copy.deepcopy(state["contract"].get("artifact_policy", {})),
        "media_extension": extension,
        "secret_scanner": SCANNER_VERSION,
    }
    if policy_extra:
        policy_snapshot.update(copy.deepcopy(policy_extra))
    artifact: dict[str, Any] = {
        "id": artifact_id,
        "availability": "available",
        "relative_path": f"raw/{artifact_id}{extension}",
        "media_type": media_type,
        "byte_size": byte_count,
        "sha256": digest,
        "sensitivity": sensitivity,
        "retention": retention,
        "include_in_html": include_in_html,
        "ingested_at": now,
        "provenance": copy.deepcopy(provenance),
        "policy_snapshot": policy_snapshot,
        "policy_sha256": sha256_hex(policy_snapshot),
        "scanner_version": SCANNER_VERSION,
    }
    if review is not None:
        artifact["redaction_review"] = review
    if host_capture is not None:
        artifact["host_capture"] = copy.deepcopy(host_capture)

    try:
        if destination.exists() or destination.is_symlink():
            raise ArtifactExists(f"artifact destination for {artifact_id} already exists")
        os.rename(temp_path, destination)
        _fsync_dir(raw_dir)
        _apply_artifact_state_patch_unlocked(
            session_dir,
            "ingest",
            [{"op": "add", "path": "/artifact_index/-", "value": artifact}],
            state["session"]["revision"],
            now,
        )
    except BaseException:
        temp_path.unlink(missing_ok=True)
        if destination.exists() and not destination.is_symlink():
            destination.unlink(missing_ok=True)
            _fsync_dir(raw_dir)
        raise
    return copy.deepcopy(artifact)


def ingest_local_artifact(
    session_dir: Path,
    source_path: Path,
    artifact_id: str,
    media_type: str,
    sensitivity: str,
    retention: str,
    include_in_html: bool,
    provenance: dict[str, Any],
    now: str,
    redaction_review: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    session_dir = Path(session_dir)
    source_path = Path(source_path)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        _load_state_unlocked(session_dir)
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise ArtifactPolicyError("event history is malformed")
        if not isinstance(provenance, dict):
            raise ArtifactPolicyError("provenance must be an object")
        origin_kind = provenance.get("origin_kind")
        if origin_kind == "local_output":
            action_id = _require_nonempty(provenance.get("action_id"), "local action_id")
            if not any(
                event.get("event") == "permit_acquired"
                and event.get("action_id") == action_id
                and event.get("category") == "local"
                and event.get("route") == "local"
                for event in events
            ):
                raise ArtifactPolicyError("local_output does not match a recorded local action")
        elif origin_kind == "user_file":
            _require_nonempty(provenance.get("supplied_by"), "user_file supplied_by")
        else:
            raise ArtifactPolicyError("local ingestion accepts only local_output or user_file")
        _reject_managed_source(session_dir, source_path)
        return _ingest_unlocked(
            session_dir,
            source_path,
            artifact_id,
            media_type,
            sensitivity,
            retention,
            include_in_html,
            provenance,
            now,
            redaction_review,
        )


def ingest_host_capture(
    session_dir: Path,
    artifact_id: str,
    source_url: str,
    source_title: str,
    upstream_key: str,
    payload: bytes,
    fidelity: str,
    captured_at: str,
    marginal_purpose: str,
    *,
    media_type: str = "application/octet-stream",
    sensitivity: str = "public",
    retention: str = "session",
    include_in_html: bool = True,
) -> dict[str, Any]:
    """Persist exact bytes returned by the host without a transaction permit.

    A host capture is an observation of the host tool's output, not a request
    sent by this repository. Its metadata is deliberately explicit about
    fidelity so host-rendered text cannot be mistaken for raw HTTP bytes.
    """

    session_dir = Path(session_dir)
    source_url = _require_nonempty(source_url, "source_url")
    source_title = _require_nonempty(source_title, "source_title")
    upstream_key = _require_nonempty(upstream_key, "upstream_key")
    try:
        source_key = canonical_source_key(source_url)
    except ValueError as exc:
        raise ArtifactPolicyError(str(exc)) from exc
    try:
        upstream_key = normalize_upstream_key(upstream_key)
    except ValueError as exc:
        raise ArtifactPolicyError(str(exc)) from exc
    purpose = _require_nonempty(marginal_purpose, "marginal_purpose")
    _require_nonempty(captured_at, "captured_at")
    if fidelity not in {"raw_http", "host_rendered"}:
        raise ArtifactPolicyError("host capture fidelity must be raw_http or host_rendered")
    if not isinstance(payload, bytes):
        raise ArtifactPolicyError("host capture payload must be bytes")

    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        contract = state.get("contract", {})
        if (
            contract.get("execution") != "host_native"
            or contract.get("durability") != "canonical_package"
            or contract.get("tier") not in {"medium", "high"}
        ):
            raise ArtifactPolicyError(
                "host captures require a host-native canonical-package Medium or High contract"
            )
        return _ingest_unlocked(
            session_dir,
            None,
            artifact_id,
            media_type,
            sensitivity,
            retention,
            include_in_html,
            {"origin_kind": "host_capture"},
            captured_at,
            None,
            {"host_capture": True},
            source_bytes=payload,
            host_capture={
                "source_url": source_url,
                "source_title": source_title,
                "canonical_source_key": source_key,
                "upstream_key": upstream_key,
                "fidelity": fidelity,
                "captured_at": captured_at,
                "marginal_purpose": purpose,
            },
        )


def ingest_fetched_source(
    session_dir: Path,
    source_path: Path,
    artifact_id: str,
    media_type: str,
    source_id: str,
    fetch_occurrence_id: str,
    sensitivity: str,
    retention: str,
    include_in_html: bool,
    now: str,
) -> dict[str, Any]:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        source = next((item for item in state["sources"] if item.get("id") == source_id), None)
        occurrence = next(
            (item for item in state["retrieval_occurrences"] if item.get("id") == fetch_occurrence_id),
            None,
        )
        if source is None or occurrence is None or occurrence.get("source_id") != source_id:
            raise ArtifactPolicyError(
                "fetched artifact requires a matching source and retrieval occurrence"
                " (patch sources and retrieval_occurrences first; pass --source-id and --fetch-occurrence-id)"
            )
        provenance = {
            "origin_kind": "fetched_source",
            "source_id": source_id,
            "fetch_occurrence_id": fetch_occurrence_id,
        }
        return _ingest_unlocked(
            session_dir,
            Path(source_path),
            artifact_id,
            media_type,
            sensitivity,
            retention,
            include_in_html,
            provenance,
            now,
            None,
        )


def promote_provider_payload(
    session_dir: Path,
    action_id: str,
    artifact_id: str,
    retention: str,
    include_in_html: bool,
    now: str,
) -> dict[str, Any]:
    """Promote a boundary-spooled provider payload into the artifact index.

    Unlike ingest_local_artifact / ingest_fetched_source, the raw bytes are
    never supplied by the caller: they are exactly what the v2 request
    boundary (research_harness.boundary) already spooled to
    provider_spool/<action_id>.raw.json when it recorded the retrieval
    occurrence for this action. Only an action that already completed
    through the boundary (a retrieval occurrence exists) can be promoted --
    there is no path from an arbitrary filesystem path to an
    evidence-capable artifact, and the generic artifact-add surface
    continues to refuse origin_kind=provider_payload outright.

    media_type and sensitivity are not caller-supplied: the spool is always
    a JSON payload (see boundary._spool_raw), and provider-sourced records
    follow the same "public" convention already used for fetched_source
    artifacts (these routes are public record-fetch APIs by registry
    construction; see storage_rights.source on each enabled provider).

    Providers whose action_categories include "deep" are refused outright:
    an async deep job's result is spooled under provider_spool/
    <poll_action_id>.raw.json by execute_deep_poll, not under the submitted
    action_id recorded on the retrieval occurrence -- that action_id's own
    spool file (if any) is only the submit-accept stub. Promoting by
    occurrence.action_id would therefore ingest the wrong bytes. Not
    supported yet.
    """

    session_dir = Path(session_dir)
    action_id = _require_nonempty(action_id, "action_id")
    # _require_nonempty only strips whitespace; it does not reject path
    # separators. quota.acquire_permits enforces the same ACTION_ID_RE at
    # permit-reservation time, but this action_id comes from a retrieval
    # occurrence, which (unlike a permit) can be written directly by a state
    # patch -- so it is re-checked here independently rather than trusted.
    if ACTION_ID_RE.fullmatch(action_id) is None:
        raise ArtifactPolicyError(
            "action_id must match ^[A-Za-z][A-Za-z0-9_-]{0,63}$ (non-empty, no path separators)"
        )
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        if state["contract"].get("artifact_policy", {}).get("allow_provider_payloads") is not True:
            raise ArtifactPolicyError("the confirmed contract forbids provider payload persistence")

        occurrence = next(
            (
                item
                for item in state.get("retrieval_occurrences", [])
                if isinstance(item, dict) and item.get("action_id") == action_id
            ),
            None,
        )
        if occurrence is None:
            raise ArtifactPolicyError(f"no retrieval occurrence is recorded for action {action_id}")
        provider_id = occurrence.get("provider_id")

        provider = next(
            (item for item in state["capabilities"]["providers"] if item.get("id") == provider_id),
            None,
        )
        preflight = next(
            (item for item in state["capabilities"]["preflight"] if item.get("provider_id") == provider_id),
            None,
        )
        if (
            provider is None
            or provider.get("enabled") is not True
            or provider.get("execution_binding") not in {"v2_request_boundary", "no_network_demo"}
            or preflight is None
            or preflight.get("ready") is not True
        ):
            raise ArtifactPolicyError("provider is not enabled and bound in the capability snapshot")
        if "deep" in (provider.get("action_categories") or []):
            raise ArtifactPolicyError(
                "deep payloads spool under poll action ids; promoting deep routes is not supported yet"
            )

        rights = provider.get("storage_rights")
        if not isinstance(rights, dict):
            raise ArtifactPolicyError("provider storage rights are missing")
        allowed_retention = rights.get("payload_retention")
        if allowed_retention not in RETENTION_RANK:
            raise ArtifactPolicyError("provider payload retention is forbidden or non-persistable")
        if retention not in RETENTIONS or RETENTION_RANK[retention] > RETENTION_RANK[allowed_retention]:
            raise ArtifactPolicyError("requested retention exceeds provider storage rights")
        if include_in_html and rights.get("html_allowed") is not True:
            raise ArtifactPolicyError("provider storage rights forbid HTML inclusion")

        # Fixed, deterministic path: the caller never names a source file.
        spool_dir = session_dir / "provider_spool"
        spool_path = spool_dir / f"{action_id}.raw.json"
        # Belt-and-suspenders: even though ACTION_ID_RE above already rejects
        # "/" and "..", confine the resolved path under provider_spool/ too,
        # so a future change to the format gate (or this action_id's origin)
        # can't reopen a path-traversal read on its own.
        if not _is_within(spool_path, spool_dir):
            raise ArtifactPolicyError("resolved provider spool path escapes provider_spool")
        provenance = {
            "origin_kind": "provider_payload",
            "provider_id": provider_id,
            "attempt_or_occurrence_id": action_id,
        }
        return _ingest_unlocked(
            session_dir,
            spool_path,
            artifact_id,
            "application/json",
            "public",
            retention,
            include_in_html,
            provenance,
            now,
            None,
            {"provider_storage_rights": rights},
        )


def _artifact_index(state: dict[str, Any], artifact_id: str) -> tuple[int, dict[str, Any]]:
    matches = [
        (index, artifact)
        for index, artifact in enumerate(state.get("artifact_index", []))
        if artifact.get("id") == artifact_id
    ]
    if len(matches) != 1:
        raise ArtifactPolicyError(f"artifact {artifact_id} does not exist uniquely")
    return matches[0]


def _affected_claim_indexes(state: dict[str, Any], artifact_id: str) -> list[tuple[int, str]]:
    evidence_ids = {
        evidence.get("id")
        for evidence in state.get("evidence", [])
        if evidence.get("artifact_id") == artifact_id and isinstance(evidence.get("id"), str)
    }
    affected: list[tuple[int, str]] = []
    for index, claim in enumerate(state.get("claims", [])):
        referenced = set(claim.get("supporting_evidence_ids", [])) | set(
            claim.get("counter_evidence_ids", [])
        )
        if evidence_ids & referenced:
            affected.append((index, claim["id"]))
    return affected


def _validate_partial_actions(
    state: dict[str, Any], safe_action_ids: tuple[str, ...], affected_claim_ids: set[str]
) -> None:
    if not isinstance(safe_action_ids, tuple) or not safe_action_ids:
        raise ArtifactPolicyError("PARTIAL purge requires a named safe reversible action")
    actions = {
        action.get("id"): action
        for action in state.get("engineering_handoff", {}).get("safe_actions", [])
        if isinstance(action, dict) and isinstance(action.get("id"), str)
    }
    for action_id in safe_action_ids:
        action = actions.get(action_id)
        dependencies = action.get("depends_on_claim_ids") if action else None
        if (
            action is None
            or action.get("reversible") is not True
            or not isinstance(dependencies, list)
            or any(not isinstance(claim_id, str) for claim_id in dependencies)
            or affected_claim_ids.intersection(dependencies)
        ):
            raise ArtifactPolicyError("PARTIAL purge action is missing, irreversible, or evidence-dependent")


def _confined_raw_path(session_dir: Path, relative_path: Any) -> Path:
    if not isinstance(relative_path, str):
        raise ArtifactPolicyError("artifact raw path is missing")
    relative = Path(relative_path)
    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "raw":
        raise ArtifactPolicyError("artifact raw path is not confined")
    raw_dir = session_dir / "raw"
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise ArtifactPolicyError("raw directory is unavailable")
    path = session_dir / relative
    if path.parent != raw_dir:
        raise ArtifactPolicyError("artifact raw path is not confined")
    return path


def _unlink_pending_bytes(session_dir: Path, pending: dict[str, Any]) -> None:
    path = _confined_raw_path(session_dir, pending.get("former_relative_path"))
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ArtifactPolicyError("pending purge target is not a regular non-symlink file")
    path.unlink()
    _fsync_dir(path.parent)


def _finalize_purge_tombstone(session_dir: Path, artifact_id: str, now: str) -> dict[str, Any]:
    state = _load_state_unlocked(session_dir)
    index, pending = _artifact_index(state, artifact_id)
    if pending.get("availability") != "purge_pending":
        raise ArtifactPolicyError("artifact is not pending purge")
    tombstone = copy.deepcopy(pending)
    tombstone["availability"] = "purged"
    tombstone["purged_at"] = now
    tombstone["requires_revalidation"] = True
    updated = _apply_artifact_state_patch_unlocked(
        session_dir,
        "purge_tombstone",
        [{"op": "replace", "path": f"/artifact_index/{index}", "value": tombstone}],
        state["session"]["revision"],
        now,
    )
    return copy.deepcopy(updated["artifact_index"][index])


def purge_raw_artifact(
    session_dir: Path,
    artifact_id: str,
    reason: str,
    requested_status: str,
    safe_action_ids: tuple[str, ...],
    now: str,
) -> dict[str, Any]:
    session_dir = Path(session_dir)
    if requested_status not in {"PARTIAL", "BLOCKED"}:
        raise ArtifactPolicyError("purge status must be PARTIAL or BLOCKED")
    reason = _require_nonempty(reason, "purge reason")
    if not isinstance(safe_action_ids, tuple) or any(
        not isinstance(action_id, str) or not action_id for action_id in safe_action_ids
    ):
        raise ArtifactPolicyError("safe_action_ids must be a tuple of non-empty strings")
    _require_nonempty(now, "now")

    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        index, artifact = _artifact_index(state, artifact_id)
        availability = artifact.get("availability")
        if availability == "purged":
            if (
                artifact.get("purge_reason") == reason
                and artifact.get("target_status") == requested_status
                and artifact.get("safe_action_ids") == list(safe_action_ids)
            ):
                return copy.deepcopy(artifact)
            raise ArtifactPolicyError("purged artifact parameters conflict with its tombstone")
        if availability == "purge_pending":
            if (
                artifact.get("purge_reason") != reason
                or artifact.get("target_status") != requested_status
                or artifact.get("safe_action_ids") != list(safe_action_ids)
            ):
                raise ArtifactPolicyError("pending purge parameters conflict with persisted authorization")
            _unlink_pending_bytes(session_dir, artifact)
            return _finalize_purge_tombstone(session_dir, artifact_id, now)
        if availability != "available":
            raise ArtifactPolicyError("artifact is not available for purge")

        raw_path = _confined_raw_path(session_dir, artifact.get("relative_path"))
        try:
            metadata = raw_path.lstat()
        except FileNotFoundError as exc:
            raise ArtifactPolicyError("available artifact bytes are missing") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ArtifactPolicyError("available artifact is not a regular non-symlink file")

        affected = _affected_claim_indexes(state, artifact_id)
        affected_ids = {claim_id for _, claim_id in affected}
        if requested_status == "PARTIAL":
            _validate_partial_actions(state, safe_action_ids, affected_ids)

        pending = copy.deepcopy(artifact)
        pending.pop("relative_path", None)
        pending.update(
            {
                "availability": "purge_pending",
                "former_relative_path": str(artifact["relative_path"]),
                "purge_reason": reason,
                "target_status": requested_status,
                "safe_action_ids": list(safe_action_ids),
                "affected_claim_ids": sorted(affected_ids),
                "purge_requested_at": now,
                "requires_revalidation": True,
            }
        )
        operations: list[dict[str, Any]] = [
            {"op": "replace", "path": f"/artifact_index/{index}", "value": pending}
        ]
        operations.extend(
            {"op": "replace", "path": f"/claims/{claim_index}/status", "value": "unverified"}
            for claim_index, _ in affected
        )
        operations.append({"op": "replace", "path": "/summary/status", "value": requested_status})
        updated = _apply_artifact_state_patch_unlocked(
            session_dir,
            "purge_pending",
            operations,
            state["session"]["revision"],
            now,
        )
        persisted = updated["artifact_index"][index]
        _unlink_pending_bytes(session_dir, persisted)
        return _finalize_purge_tombstone(session_dir, artifact_id, now)


def recover_pending_purges(session_dir: Path, now: str) -> list[dict[str, Any]]:
    session_dir = Path(session_dir)
    _require_nonempty(now, "now")
    recovered: list[dict[str, Any]] = []
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        pending_ids = [
            artifact.get("id")
            for artifact in _load_state_unlocked(session_dir).get("artifact_index", [])
            if artifact.get("availability") == "purge_pending"
        ]
        for artifact_id in pending_ids:
            if not isinstance(artifact_id, str):
                raise ArtifactPolicyError("pending purge artifact has no valid ID")
            _, pending = _artifact_index(_load_state_unlocked(session_dir), artifact_id)
            _unlink_pending_bytes(session_dir, pending)
            recovered.append(_finalize_purge_tombstone(session_dir, artifact_id, now))
    return recovered
