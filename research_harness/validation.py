"""Fail-closed validation for canonical v2 research sessions."""

from __future__ import annotations

import hashlib
import html
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ._canon import RETENTION_RANK, indexed, sha256_hex
from .artifacts import MEDIA_EXTENSIONS, SCANNER_VERSION
from .state import state_sha256, validate_state_document
from .storage import (
    _event_chain_errors,
    _load_state_unlocked,
    _read_events_unlocked,
    _recover_session_unlocked,
    session_lock,
)


PASSING_CLAIM_STATUSES = frozenset({"corroborated"})
VALID_DELIVERY_STATUSES = frozenset({"IN_PROGRESS", "PASS", "PARTIAL", "BLOCKED"})
REPORT_HASH_RE = re.compile(r'data-state-sha256=["\']([0-9a-f]{64})["\']')


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str
    path: str


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[Issue, ...]
    state_sha256: str

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(issue for issue in self.issues if issue.level == "ERROR")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(issue for issue in self.issues if issue.level == "WARNING")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "state_sha256": self.state_sha256,
            "issues": [asdict(issue) for issue in self.issues],
            "errors": [asdict(issue) for issue in self.errors],
            "warnings": [asdict(issue) for issue in self.warnings],
        }


def _add(
    issues: list[Issue],
    code: str,
    message: str,
    path: str,
    level: str = "ERROR",
) -> None:
    issues.append(Issue(level=level, code=code, message=message, path=path))


def _validate_event_lineage(
    state: dict[str, Any],
    events: list[dict[str, Any]],
    event_errors: list[str],
    current_hash: str,
    issues: list[Issue],
) -> None:
    chain_errors = [] if event_errors else _event_chain_errors(events)
    for message in event_errors:
        _add(issues, "event.parse", message, "/events")
    for message in chain_errors:
        _add(issues, "event.chain", message, "/events")
    if event_errors or chain_errors:
        return

    genesis = [event for event in events if event.get("event") == "session_created"]
    if len(genesis) != 1 or genesis[0].get("session_id") != state.get("session", {}).get("id"):
        _add(issues, "state.genesis", "session genesis event is missing or inconsistent", "/events")
    revisions = [event for event in events if event.get("event") == "state_revision"]
    revision = state.get("session", {}).get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool):
        return
    expected = list(range(1, revision + 1))
    observed = [event.get("revision") for event in revisions]
    if observed != expected:
        _add(issues, "state.revision_lineage", "state revision events are not exact and monotonic", "/events")
    if revision == 0:
        if len(genesis) == 1 and genesis[0].get("state_sha256") != current_hash:
            _add(issues, "state.hash_mismatch", "genesis hash does not match canonical state", "/state")
    elif not revisions or revisions[-1].get("new_state_sha256") != current_hash:
        _add(issues, "state.hash_mismatch", "latest revision hash does not match canonical state", "/state")


def _validate_quota(
    state: dict[str, Any], events: list[dict[str, Any]], issues: list[Issue]
) -> None:
    contract = state.get("contract", {})
    mappings = contract.get("stage_permit_map", [])
    providers = {
        provider.get("id"): provider
        for provider in state.get("capabilities", {}).get("providers", [])
        if isinstance(provider, dict)
    }
    ceilings = contract.get("resource_envelope", {}).get("physical_ceiling", {})
    permits = [event for event in events if event.get("event") == "permit_acquired"]
    seen_actions: set[str] = set()
    category_usage: dict[str, int] = {}
    mapping_usage: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for index, permit in enumerate(permits):
        path = f"/events/permit/{index}"
        action_id = permit.get("action_id")
        if not isinstance(action_id, str) or not action_id or action_id in seen_actions:
            _add(issues, "quota.duplicate", "permit action IDs must be unique and non-empty", path)
        elif isinstance(action_id, str):
            seen_actions.add(action_id)
        count = permit.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            _add(issues, "quota.invalid", "permit count must be a positive integer", path)
            continue
        category = permit.get("category")
        route = permit.get("route")
        stage = permit.get("stage")
        key = (stage, category, route)
        matching = [
            mapping
            for mapping in mappings
            if isinstance(mapping, dict)
            and (mapping.get("stage"), mapping.get("category"), mapping.get("route")) == key
        ]
        if len(matching) != 1:
            _add(issues, "quota.mapping", "permit has no unique confirmed stage mapping", path)
        mapping_usage.setdefault(key, []).append(permit)
        category_usage[category] = category_usage.get(category, 0) + count
        provider = providers.get(route)
        multiplicity = provider.get("request_multiplicity", {}).get(category) if provider else None
        if multiplicity != count:
            _add(issues, "quota.multiplicity", "permit count differs from route multiplicity", path)

    for key, used in mapping_usage.items():
        mapping = next(
            (
                item
                for item in mappings
                if isinstance(item, dict)
                and (item.get("stage"), item.get("category"), item.get("route")) == key
            ),
            None,
        )
        if mapping is None:
            continue
        request_count = sum(item["count"] for item in used if isinstance(item.get("count"), int))
        if len(used) > mapping.get("invocations", -1) or request_count > mapping.get("count", -1):
            _add(issues, "quota.exceeded", "stage mapping capacity was exceeded", "/events")
    for category, used in category_usage.items():
        ceiling = ceilings.get(category)
        if not isinstance(ceiling, int) or isinstance(ceiling, bool) or used > ceiling:
            _add(issues, "quota.exceeded", f"physical ceiling exceeded for {category}", "/events")


def _confined_artifact_path(session_dir: Path, relative_path: Any) -> Path | None:
    if not isinstance(relative_path, str):
        return None
    relative = Path(relative_path)
    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "raw":
        return None
    path = session_dir / relative
    if path.parent != session_dir / "raw":
        return None
    return path


def _validate_artifacts(
    session_dir: Path,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    issues: list[Issue],
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    artifacts = indexed(state.get("artifact_index"))
    sources = indexed(state.get("sources"))
    occurrences = indexed(state.get("retrieval_occurrences"))
    providers = indexed(state.get("capabilities", {}).get("providers"))
    permits = [event for event in events if event.get("event") == "permit_acquired"]
    indexed_paths: set[str] = set()
    raw_payloads: dict[str, bytes] = {}

    for artifact_id, artifact in artifacts.items():
        path_root = f"/artifact_index/{artifact_id}"
        availability = artifact.get("availability")
        if availability == "purge_pending":
            _add(issues, "artifact.purge_pending", "artifact purge recovery is incomplete", path_root)
        if availability not in {"available", "purge_pending", "purged"}:
            _add(issues, "artifact.availability", "artifact availability is invalid", path_root)
        relative_key = "relative_path" if availability == "available" else "former_relative_path"
        raw_path = _confined_artifact_path(session_dir, artifact.get(relative_key))
        if raw_path is None:
            _add(issues, "artifact.path", "artifact path is not confined under raw", path_root)
        else:
            indexed_paths.add(raw_path.name)
            extension = MEDIA_EXTENSIONS.get(artifact.get("media_type"))
            if extension is None or raw_path.name != f"{artifact_id}{extension}":
                _add(issues, "artifact.path", "artifact path does not match its ID and media type", path_root)
        policy = artifact.get("policy_snapshot")
        expected_policy_hash = sha256_hex(policy) if isinstance(policy, dict) else None
        if artifact.get("policy_sha256") != expected_policy_hash:
            _add(issues, "artifact.policy_hash", "artifact policy snapshot hash is invalid", path_root)
        if artifact.get("scanner_version") != SCANNER_VERSION:
            _add(issues, "artifact.scanner", "artifact scanner version is missing or unknown", path_root)
        if artifact.get("sensitivity") == "secret":
            _add(issues, "artifact.secret", "secret-classified artifacts cannot be persisted", path_root)
        if artifact.get("sensitivity") == "local-sensitive" and artifact.get("include_in_html") is not False:
            _add(issues, "artifact.html_policy", "local-sensitive artifact cannot enter HTML", path_root)

        if availability == "available" and raw_path is not None:
            try:
                metadata = raw_path.lstat()
            except FileNotFoundError:
                _add(issues, "artifact.raw_missing", "available raw artifact is missing", path_root)
            else:
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    _add(issues, "artifact.path", "raw artifact is not a regular non-symlink file", path_root)
                else:
                    payload = raw_path.read_bytes()
                    raw_payloads[artifact_id] = payload
                    if (
                        metadata.st_size != artifact.get("byte_size")
                        or hashlib.sha256(payload).hexdigest() != artifact.get("sha256")
                    ):
                        _add(issues, "artifact.integrity", "raw artifact size or hash changed", path_root)

        provenance = artifact.get("provenance")
        if not isinstance(provenance, dict):
            _add(issues, "artifact.provenance", "artifact provenance is missing", path_root)
            continue
        origin_kind = provenance.get("origin_kind")
        if origin_kind == "local_output":
            action_id = provenance.get("action_id")
            if not any(
                permit.get("action_id") == action_id
                and permit.get("category") == "local"
                and permit.get("route") == "local"
                for permit in permits
            ):
                _add(issues, "artifact.provenance", "local artifact action is missing", path_root)
        elif origin_kind == "user_file":
            if not isinstance(provenance.get("supplied_by"), str) or not provenance["supplied_by"]:
                _add(issues, "artifact.provenance", "user artifact supplier is missing", path_root)
        elif origin_kind == "fetched_source":
            source_id = provenance.get("source_id")
            occurrence = occurrences.get(provenance.get("fetch_occurrence_id"))
            if source_id not in sources or occurrence is None or occurrence.get("source_id") != source_id:
                _add(issues, "artifact.provenance", "fetched artifact lineage is missing", path_root)
        elif origin_kind == "provider_payload":
            provider_id = provenance.get("provider_id")
            attempt_id = provenance.get("attempt_or_occurrence_id")
            provider = providers.get(provider_id)
            matched = any(
                permit.get("action_id") == attempt_id and permit.get("route") == provider_id
                for permit in permits
            ) or (
                attempt_id in occurrences and occurrences[attempt_id].get("provider_id") == provider_id
            )
            rights = provider.get("storage_rights", {}) if provider else {}
            allowed = rights.get("payload_retention")
            requested = artifact.get("retention")
            if provider is None or not matched:
                _add(issues, "artifact.provenance", "provider artifact lineage is missing", path_root)
            if (
                allowed not in {"session", "persistent"}
                or requested not in {"session", "persistent"}
                or RETENTION_RANK[requested] > RETENTION_RANK[allowed]
                or (artifact.get("include_in_html") and rights.get("html_allowed") is not True)
            ):
                _add(issues, "artifact.storage_rights", "provider artifact exceeds storage rights", path_root)
        else:
            _add(issues, "artifact.provenance", "artifact origin kind is invalid", path_root)

    raw_dir = session_dir / "raw"
    if raw_dir.exists():
        if raw_dir.is_symlink() or not raw_dir.is_dir():
            _add(issues, "artifact.raw_directory", "raw path is not a safe directory", "/raw")
        else:
            for path in raw_dir.iterdir():
                if path.name not in indexed_paths:
                    _add(issues, "artifact.unindexed", f"unindexed raw entry: {path.name}", "/raw")
    return artifacts, raw_payloads


def _validate_evidence(
    state: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    raw_payloads: dict[str, bytes],
    issues: list[Issue],
) -> dict[str, dict[str, Any]]:
    evidence_map = indexed(state.get("evidence"))
    sources = indexed(state.get("sources"))
    origins = indexed(state.get("source_origins"))
    providers = indexed(state.get("capabilities", {}).get("providers"))
    occurrences = state.get("retrieval_occurrences", [])

    for evidence_id, evidence in evidence_map.items():
        path = f"/evidence/{evidence_id}"
        source = sources.get(evidence.get("source_id"))
        if source is None:
            _add(issues, "evidence.source_missing", "evidence source is missing", path)
        origin_id = evidence.get("origin_id")
        if origin_id not in origins or (source and source.get("origin_id") != origin_id):
            _add(issues, "evidence.origin_missing", "evidence source origin is missing or inconsistent", path)
        artifact_id = evidence.get("artifact_id")
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            _add(issues, "evidence.artifact_missing", "evidence artifact record is missing", path)
        provenance = artifact.get("provenance", {}) if artifact is not None else {}
        if provenance.get("origin_kind") == "provider_payload":
            provider = providers.get(provenance.get("provider_id"))
            if (
                provider is None
                or provider.get("evidence_capabilities", {}).get("can_support_claims") is not True
            ):
                _add(
                    issues,
                    "evidence.provider_claims_forbidden",
                    "this provider payload cannot support canonical claims",
                    path,
                )
        payload = raw_payloads.get(artifact_id)
        start = evidence.get("excerpt_start")
        end = evidence.get("excerpt_end")
        excerpt = evidence.get("excerpt")
        artifact_was_purged = artifact is not None and artifact.get("availability") in {
            "purge_pending",
            "purged",
        }
        if artifact_was_purged:
            pass
        elif (
            payload is None
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
            or end > (len(payload) if payload is not None else 0)
            or not isinstance(excerpt, str)
        ):
            _add(issues, "evidence.excerpt_bounds", "exact raw excerpt bounds are invalid", path)
        else:
            try:
                exact = payload[start:end].decode("utf-8")
            except UnicodeDecodeError:
                exact = None
            if exact != excerpt:
                _add(issues, "evidence.excerpt_mismatch", "excerpt does not match raw artifact bytes", path)

        source_id = evidence.get("source_id")
        source_occurrences = [
            occurrence
            for occurrence in occurrences
            if isinstance(occurrence, dict) and occurrence.get("source_id") == source_id
        ]
        if any(
            providers.get(occurrence.get("provider_id"), {}).get("execution_binding")
            == "no_network_demo"
            for occurrence in source_occurrences
        ):
            _add(
                issues,
                "evidence.demo_route_forbidden",
                "no-network demo routes cannot contribute canonical evidence",
                path,
            )
    return evidence_map


def _has_direct_t1_evidence(
    evidence_ids: Any,
    evidence_map: dict[str, dict[str, Any]],
    sources: dict[str, dict[str, Any]],
) -> bool:
    """True when any supporting evidence is a directly fetched T1 source."""

    return any(
        evidence_map.get(evidence_id, {}).get("source_tier") == "T1"
        and sources.get(evidence_map.get(evidence_id, {}).get("source_id"), {}).get("direct_fetch") is True
        for evidence_id in (evidence_ids if isinstance(evidence_ids, list) else [])
    )


def _claim_has_available_evidence(
    claim: dict[str, Any],
    evidence_map: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    raw_payloads: dict[str, bytes],
) -> bool:
    for evidence_id in claim.get("supporting_evidence_ids", []):
        evidence = evidence_map.get(evidence_id)
        artifact = artifacts.get(evidence.get("artifact_id")) if evidence else None
        if (
            artifact
            and artifact.get("availability") == "available"
            and evidence.get("artifact_id") in raw_payloads
        ):
            return True
    return False


def _validate_pass(
    state: dict[str, Any],
    events: list[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    raw_payloads: dict[str, bytes],
    evidence_map: dict[str, dict[str, Any]],
    issues: list[Issue],
) -> None:
    summary = state.get("summary", {})
    decision = summary.get("decision")
    admitted = state.get("contract", {}).get("resource_envelope", {}).get("host", {}).get(
        "admitted_characters"
    )
    if not isinstance(decision, str) or not decision.strip():
        _add(issues, "status.pass_answer_missing", "PASS requires a non-empty bounded answer", "/summary/decision")
    elif isinstance(admitted, int) and len(decision) > admitted:
        _add(issues, "status.pass_answer_unbounded", "PASS answer exceeds the confirmed host envelope", "/summary/decision")

    load_ids = summary.get("load_bearing_claim_ids")
    if not isinstance(load_ids, list) or not load_ids:
        _add(issues, "status.pass_claim_set_empty", "PASS requires load-bearing claims", "/summary")
        load_ids = []
    claims = indexed(state.get("claims"))
    marked = {claim_id for claim_id, claim in claims.items() if claim.get("load_bearing") is True}
    if set(load_ids) != marked:
        _add(issues, "status.pass_claim_set_mismatch", "summary and claim load-bearing markers differ", "/summary")
    floor = state.get("contract", {}).get("evidence_floor", {}).get("minimum_load_bearing_claims")
    if not isinstance(floor, int) or isinstance(floor, bool) or len(load_ids) < floor:
        _add(issues, "status.evidence_floor", "confirmed evidence floor is not satisfied", "/summary")

    sources = indexed(state.get("sources"))
    origins = indexed(state.get("source_origins"))
    for claim_id in load_ids:
        claim = claims.get(claim_id)
        path = f"/claims/{claim_id}"
        if claim is None:
            continue
        if claim.get("status") not in PASSING_CLAIM_STATUSES:
            _add(issues, "claim.status", "load-bearing claim status cannot clear PASS", path)
        claim_type = claim.get("claim_type")
        if claim_type not in {"source-of-record", "empirical", "local-observation"}:
            _add(issues, "claim.type", "load-bearing claim type is missing or invalid", path)
        supporting = claim.get("supporting_evidence_ids")
        if not isinstance(supporting, list) or not supporting:
            _add(issues, "claim.evidence_missing", "load-bearing claim has no supporting evidence", path)
            continue
        if not _claim_has_available_evidence(claim, evidence_map, artifacts, raw_payloads):
            _add(issues, "claim.raw_missing", "load-bearing claim has no available raw artifact", path)
        if claim.get("applicability") != "checked":
            _add(issues, "claim.applicability", "load-bearing claim applicability is not checked", path)
        origin_ids = claim.get("source_origin_ids")
        if not isinstance(origin_ids, list) or not origin_ids:
            _add(issues, "claim.origin_missing", "load-bearing claim has no source origin", path)
        evidence_origins = {
            evidence_map[evidence_id].get("origin_id")
            for evidence_id in supporting
            if evidence_id in evidence_map
        }
        if isinstance(origin_ids, list) and set(origin_ids) != evidence_origins:
            _add(issues, "claim.origin_mismatch", "claim origins differ from supporting evidence", path)
        if claim_type == "empirical":
            independent = {
                origin_id
                for origin_id in evidence_origins
                if origins.get(origin_id, {}).get("independent") is True
            }
            if len(independent) < 2:
                _add(
                    issues,
                    "claim.origin_independence",
                    "empirical load-bearing claims require two independent source origins",
                    path,
                )
        for evidence_id in supporting:
            evidence = evidence_map.get(evidence_id)
            if evidence is None:
                continue
            if evidence.get("entailment") != "entailed":
                _add(issues, "claim.entailment", "load-bearing evidence is not marked entailing", path)
            if evidence.get("applicability") != "checked":
                _add(issues, "claim.applicability", "load-bearing evidence applicability is not checked", path)
        if claim_type == "source-of-record" and not _has_direct_t1_evidence(supporting, evidence_map, sources):
            _add(
                issues,
                "claim.source_of_record_missing",
                "source-of-record claim requires a directly fetched T1 source",
                path,
            )

    contract = state.get("contract", {})
    posture = contract.get("posture")
    tier = contract.get("tier")
    verification = [item for item in state.get("verification", []) if isinstance(item, dict)]
    if posture == "lookup":
        for claim_id in load_ids:
            claim = claims.get(claim_id, {})
            if not _has_direct_t1_evidence(claim.get("supporting_evidence_ids"), evidence_map, sources):
                _add(issues, "posture.lookup_primary_missing", "lookup PASS requires a directly fetched T1 source", f"/claims/{claim_id}")
    if posture in {"scientific", "decision"} and tier in {"medium", "high"}:
        if not any(item.get("kind") == "anti_lock_in" and item.get("completed") is True for item in verification):
            _add(issues, "tier.anti_lock_in_missing", "anti-lock-in checkpoint is missing", "/verification")
        if not any(
            item.get("kind") == "coverage_audit"
            and item.get("completed") is True
            and item.get("candidate_omissions_dispositioned") is True
            for item in verification
        ):
            _add(issues, "tier.coverage_audit_missing", "coverage audit is incomplete", "/verification")
    if posture == "decision" and not any(
        isinstance(joint, dict)
        and joint.get("weakest_joint") is True
        and joint.get("adversarially_reviewed") is True
        for joint in state.get("inference_joints", [])
    ):
        _add(issues, "posture.decision_joint_missing", "decision inference joint review is missing", "/inference_joints")
    high_verifiers = [
        item
        for item in verification
        if item.get("kind") == "verifier"
        and item.get("completed") is True
        and item.get("context_separated") is True
        and item.get("produced_candidate") is False
    ]
    if tier == "high" and not high_verifiers:
        _add(issues, "tier.high_verifier_missing", "High PASS requires a context-separated verifier", "/verification")
    elif tier == "high":
        bound_actions = {
            event.get("action_id")
            for event in events
            if event.get("event") == "permit_acquired"
            and event.get("stage") == "context_separated_verification"
            and event.get("category") == "organizer_pass"
            and event.get("route") == "host"
        }
        completed_actions = {
            event.get("action_id")
            for event in events
            if event.get("event") == "attempt_status" and event.get("status") == "completed"
        }
        if not any(
            verifier.get("action_id") in bound_actions & completed_actions
            for verifier in high_verifiers
        ):
            _add(
                issues,
                "tier.high_verifier_unbound",
                "High verifier is not bound to a completed reserved verifier action",
                "/verification",
            )


def _validate_partial(
    state: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    raw_payloads: dict[str, bytes],
    evidence_map: dict[str, dict[str, Any]],
    issues: list[Issue],
) -> None:
    load_ids = set(state.get("summary", {}).get("load_bearing_claim_ids", []))
    claims = indexed(state.get("claims"))
    unresolved = {
        claim_id
        for claim_id in load_ids
        if claim_id not in claims
        or claims[claim_id].get("status") not in PASSING_CLAIM_STATUSES
        or not _claim_has_available_evidence(
            claims[claim_id], evidence_map, artifacts, raw_payloads
        )
    }
    safe = False
    for action in state.get("engineering_handoff", {}).get("safe_actions", []):
        dependencies = action.get("depends_on_claim_ids") if isinstance(action, dict) else None
        if (
            isinstance(action, dict)
            and isinstance(action.get("id"), str)
            and action["id"]
            and action.get("reversible") is True
            and isinstance(dependencies, list)
            and not unresolved.intersection(dependencies)
        ):
            safe = True
            break
    if not safe:
        _add(
            issues,
            "status.partial_safe_action_missing",
            "PARTIAL requires a reversible action independent of every unresolved gap",
            "/engineering_handoff/safe_actions",
        )


def _validate_report_hash(
    session_dir: Path, current_hash: str, issues: list[Issue]
) -> None:
    report_path = session_dir / "report.html"
    if not report_path.exists():
        return
    if report_path.is_symlink() or not report_path.is_file():
        _add(issues, "report.invalid", "report.html is not a regular file", "/report.html")
        return
    try:
        document = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _add(issues, "report.invalid", "report.html cannot be read as UTF-8", "/report.html")
        return
    match = REPORT_HASH_RE.search(html.unescape(document))
    if match is None or match.group(1) != current_hash:
        _add(issues, "report.stale", "report.html is not bound to the current canonical state", "/report.html")


def _validate_loaded_session(
    session_dir: Path,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    event_errors: list[str],
    check_report: bool,
) -> ValidationReport:
    session_dir = Path(session_dir)
    issues: list[Issue] = []
    current_hash = state_sha256(state)
    for message in validate_state_document(state):
        _add(issues, "state.structural", message, "/state")
    _validate_event_lineage(state, events, event_errors, current_hash, issues)
    _validate_quota(state, events, issues)
    artifacts, raw_payloads = _validate_artifacts(session_dir, state, events, issues)
    evidence_map = _validate_evidence(state, artifacts, raw_payloads, issues)

    status = state.get("summary", {}).get("status")
    if status not in VALID_DELIVERY_STATUSES:
        _add(issues, "status.invalid", "delivery status is invalid", "/summary/status")
    elif status == "PASS":
        _validate_pass(state, events, artifacts, raw_payloads, evidence_map, issues)
    elif status == "PARTIAL":
        _validate_partial(state, artifacts, raw_payloads, evidence_map, issues)
    if check_report:
        _validate_report_hash(session_dir, current_hash, issues)
    return ValidationReport(tuple(issues), current_hash)


def validate_session(session_dir: Path, check_report: bool = True) -> ValidationReport:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, event_errors = _read_events_unlocked(session_dir)
        return _validate_loaded_session(session_dir, state, events, event_errors, check_report)
