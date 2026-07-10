"""Public compound operations that always revalidate and rerender."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import purge_raw_artifact, recover_pending_purges
from .rendering import RenderedReport, render_session_result
from .storage import recover_session


def _rendered_payload(rendered: RenderedReport) -> dict[str, Any]:
    return {
        "validation": rendered.validation.to_dict(),
        "state_sha256": rendered.state_sha256,
        "report_sha256": rendered.report_sha256,
        "report_path": str(rendered.path.resolve()),
    }


def purge_artifact(
    session_dir: Path,
    artifact_id: str,
    reason: str,
    requested_status: str = "BLOCKED",
    safe_action_ids: tuple[str, ...] = (),
    now: str = "",
) -> dict[str, Any]:
    tombstone = purge_raw_artifact(
        Path(session_dir),
        artifact_id,
        reason,
        requested_status,
        safe_action_ids,
        now,
    )
    rendered = render_session_result(Path(session_dir))
    return {"tombstone": tombstone, **_rendered_payload(rendered)}


def recover_operation(session_dir: Path, now: str) -> dict[str, Any]:
    session_dir = Path(session_dir)
    storage_recovery = recover_session(session_dir)
    purges = recover_pending_purges(session_dir, now)
    rendered = render_session_result(session_dir)
    return {
        "storage_recovery": storage_recovery,
        "recovered_purges": purges,
        **_rendered_payload(rendered),
    }
