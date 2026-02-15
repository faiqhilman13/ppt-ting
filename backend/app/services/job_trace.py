from __future__ import annotations

import hashlib
import json
from datetime import datetime
from time import perf_counter
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import JobEvent, QualityReport, ToolRun


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def _sha1_json(value: Any) -> str:
    raw = _safe_json(value)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def record_job_event(
    *,
    job_id: str,
    stage: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    severity: str = "info",
) -> None:
    if not settings.persist_job_events:
        return
    db = SessionLocal()
    try:
        row = JobEvent(
            job_id=job_id,
            ts=datetime.utcnow(),
            stage=stage,
            event_type=event_type,
            payload_json=_safe_json(payload),
            severity=severity,
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def list_job_events(job_id: str, *, limit: int = 400) -> list[JobEvent]:
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.ts.asc(), JobEvent.id.asc())
            .limit(max(1, min(limit, settings.job_events_page_size)))
        ).all()
        return rows
    finally:
        db.close()


def decode_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json:
        return {}
    try:
        parsed = json.loads(payload_json)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {}


class ToolRunRecorder:
    def __init__(self, *, job_id: str, tool_name: str, input_payload: dict[str, Any] | None = None):
        self.job_id = job_id
        self.tool_name = tool_name
        self.input_payload = input_payload or {}
        self.started = perf_counter()

    def finish(
        self,
        *,
        status: str,
        output_payload: dict[str, Any] | None = None,
        artifacts: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if not settings.persist_tool_runs:
            return
        if not self.job_id or self.job_id == "n/a":
            return
        elapsed_ms = int((perf_counter() - self.started) * 1000)
        db = SessionLocal()
        try:
            row = ToolRun(
                job_id=self.job_id,
                tool_name=self.tool_name,
                status=status,
                duration_ms=elapsed_ms,
                input_hash=_sha1_json(self.input_payload),
                output_hash=_sha1_json(output_payload or {}),
                artifact_json=_safe_json(artifacts or {}),
                error=error,
            )
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


def upsert_quality_report(
    *,
    deck_id: str,
    version: int,
    score: float | None,
    issues: dict[str, Any],
    passes_used: int,
) -> None:
    db = SessionLocal()
    try:
        row = db.scalar(
            select(QualityReport).where(
                QualityReport.deck_id == deck_id,
                QualityReport.version == version,
            )
        )
        if row is None:
            row = QualityReport(
                deck_id=deck_id,
                version=version,
                score=score,
                issues_json=_safe_json(issues),
                passes_used=passes_used,
            )
            db.add(row)
        else:
            row.score = score
            row.issues_json = _safe_json(issues)
            row.passes_used = passes_used
            db.add(row)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
