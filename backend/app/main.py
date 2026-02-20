from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, SessionLocal, engine, get_db
from app.models import Deck, DeckJob, DeckOutline, DeckVersion, DocumentAsset, JobEvent, QualityReport, Template
from app.schemas import (
    DeckDetailOut,
    DeckOut,
    DocumentOut,
    EditorCallbackPayload,
    EditorSessionOut,
    EditorSessionRequest,
    GenerateDeckRequest,
    JobEventOut,
    JobOut,
    JsonRenderDemoQueryOut,
    JsonRenderDemoQueryRequest,
    OutlineDeckRequest,
    OutlineResultOut,
    QualityReportOut,
    ReviseDeckRequest,
    SearchRequest,
    SearchResult,
    TemplateCleanupOut,
    TemplateCleanupRequest,
    TemplateDeleteOut,
    TemplateOut,
)
from app.services.doc_extractor import SUPPORTED_EXTENSIONS, extract_text
from app.services.editor_service import build_editor_config
from app.services.job_trace import decode_payload
from app.services.json_render_agent_service import run_agentic_json_render_query
from app.services.json_render_demo_service import ensure_json_render_demo_seeded, run_json_render_demo_query
from app.services.research_service import search_web
from app.services.template_service import parse_template_manifest
from app.storage import make_file_path, read_json, write_json
from app.tasks import run_generation_job, run_outline_job, run_revision_job
from app.tools import register_builtin_tools

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_TEST_TEMPLATE_NAME_RE = re.compile(
    r"\b(smoke|fidelity|para\s*clone|plain\s*template|test)\b",
    re.IGNORECASE,
)


class _AccessLogPathFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not settings.suppress_job_poll_access_logs:
            return True

        message = record.getMessage()
        if '"GET /api/jobs/' in message:
            return False
        if '"OPTIONS /api/jobs/' in message:
            return False
        return True


def _configure_runtime_logging() -> None:
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    logging.getLogger("ppt_agent").setLevel(level)
    logging.getLogger("ppt_agent.jobs").setLevel(level)
    logging.getLogger("ppt_agent.providers").setLevel(level)
    logging.getLogger("ppt_agent.json_render_agent").setLevel(level)

    if settings.suppress_httpx_info_logs:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("anthropic").setLevel(logging.WARNING)

    access_logger = logging.getLogger("uvicorn.access")
    if settings.suppress_job_poll_access_logs and not any(
        isinstance(row, _AccessLogPathFilter) for row in access_logger.filters
    ):
        access_logger.addFilter(_AccessLogPathFilter())


@app.on_event("startup")
def on_startup():
    _configure_runtime_logging()
    register_builtin_tools()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_json_render_demo_seeded(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


def _is_internal_template(row: Template) -> bool:
    return str(row.status or "").lower().startswith("scratch")


def _is_test_template(row: Template) -> bool:
    return bool(_TEST_TEMPLATE_NAME_RE.search(str(row.name or "")))


def _is_hidden_template(row: Template) -> bool:
    status = str(row.status or "").lower()
    if status in {"archived", "deleted"}:
        return True
    return _is_internal_template(row) or _is_test_template(row)


def _delete_template_files(*paths: str) -> list[str]:
    deleted: list[str] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw)
        if not path.exists() or not path.is_file():
            continue
        try:
            path.unlink()
            deleted.append(str(path))
        except OSError:
            continue
    return deleted


@app.post(f"{settings.api_prefix}/templates", response_model=TemplateOut)
async def upload_template(name: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx templates are supported")

    template_id = str(uuid4())
    file_path = make_file_path("templates", "pptx", stem=template_id)
    file_path.write_bytes(await file.read())

    manifest = parse_template_manifest(file_path)
    manifest_path = make_file_path("manifests", "json", stem=f"template-{template_id}")
    write_json(manifest_path, manifest)

    row = Template(id=template_id, name=name, file_path=str(file_path), manifest_path=str(manifest_path), status="active")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get(f"{settings.api_prefix}/templates", response_model=list[TemplateOut])
def list_templates(include_hidden: bool = Query(default=False), db: Session = Depends(get_db)):
    rows = db.scalars(select(Template).order_by(Template.created_at.desc())).all()
    if include_hidden:
        return rows
    return [row for row in rows if not _is_hidden_template(row)]


@app.delete(f"{settings.api_prefix}/templates/{{template_id}}", response_model=TemplateDeleteOut)
def delete_template(template_id: str, db: Session = Depends(get_db)):
    row = db.get(Template, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    deck_count = db.scalar(
        select(func.count()).select_from(Deck).where(Deck.template_id == template_id)
    ) or 0
    if deck_count:
        # Keep referenced templates for revision/history integrity, but archive them
        # so they disappear from the default template list.
        if str(row.status or "").lower() != "archived":
            row.status = "archived"
            db.add(row)
            db.commit()
        return TemplateDeleteOut(template_id=template_id, deleted=False, archived=True, deleted_files=[])

    file_path = row.file_path
    manifest_path = row.manifest_path
    db.delete(row)
    db.commit()

    deleted_files = _delete_template_files(file_path, manifest_path)
    return TemplateDeleteOut(template_id=template_id, deleted=True, archived=False, deleted_files=deleted_files)


@app.post(f"{settings.api_prefix}/templates/cleanup", response_model=TemplateCleanupOut)
def cleanup_templates(req: TemplateCleanupRequest, db: Session = Depends(get_db)):
    rows = db.scalars(select(Template).order_by(Template.created_at.desc())).all()
    deck_counts = {
        template_id: count
        for template_id, count in db.execute(
            select(Deck.template_id, func.count(Deck.id)).group_by(Deck.template_id)
        ).all()
    }

    matched_rows: list[Template] = []
    skipped: list[dict[str, str]] = []
    for row in rows:
        is_internal = _is_internal_template(row)
        is_test = _is_test_template(row)
        if not ((req.include_scratch and is_internal) or (req.include_test and is_test)):
            continue

        deck_count = int(deck_counts.get(row.id, 0))
        if req.only_unreferenced and deck_count > 0:
            skipped.append(
                {
                    "template_id": row.id,
                    "name": row.name,
                    "reason": f"in_use:{deck_count}",
                }
            )
            continue

        matched_rows.append(row)

    matched_ids = [row.id for row in matched_rows]
    if req.dry_run or not matched_rows:
        return TemplateCleanupOut(
            dry_run=req.dry_run,
            matched_ids=matched_ids,
            deleted_ids=[],
            deleted_file_count=0,
            skipped=skipped,
        )

    template_files = [(row.file_path, row.manifest_path) for row in matched_rows]
    deleted_ids: list[str] = []
    for row in matched_rows:
        db.delete(row)
        deleted_ids.append(row.id)
    db.commit()

    deleted_files: list[str] = []
    for file_path, manifest_path in template_files:
        deleted_files.extend(_delete_template_files(file_path, manifest_path))

    return TemplateCleanupOut(
        dry_run=False,
        matched_ids=matched_ids,
        deleted_ids=deleted_ids,
        deleted_file_count=len(deleted_files),
        skipped=skipped,
    )


@app.post(f"{settings.api_prefix}/docs", response_model=DocumentOut)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported extension. Allowed: {sorted(SUPPORTED_EXTENSIONS)}")

    doc_id = str(uuid4())
    path = make_file_path("uploads", suffix, stem=doc_id)
    path.write_bytes(await file.read())

    text = extract_text(path)
    extracted_path = make_file_path("manifests", "txt", stem=f"doc-{doc_id}")
    extracted_path.write_text(text, encoding="utf-8")

    row = DocumentAsset(id=doc_id, filename=file.filename, file_path=str(path), extracted_text_path=str(extracted_path))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get(f"{settings.api_prefix}/docs", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.scalars(select(DocumentAsset).order_by(DocumentAsset.created_at.desc())).all()


@app.post(f"{settings.api_prefix}/decks/generate", response_model=JobOut)
def generate_deck(req: GenerateDeckRequest, db: Session = Depends(get_db)):
    if req.creation_mode == "template":
        template = db.get(Template, req.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

    for doc_id in req.doc_ids:
        if not db.get(DocumentAsset, doc_id):
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    job = DeckJob(
        id=str(uuid4()),
        job_type="generate",
        status="queued",
        phase="queued",
        progress_pct=0,
        payload_json=req.model_dump_json(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    run_generation_job.delay(job.id)
    return job


@app.post(f"{settings.api_prefix}/decks/outline", response_model=JobOut)
def generate_outline(req: OutlineDeckRequest, db: Session = Depends(get_db)):
    if req.creation_mode == "template":
        template = db.get(Template, req.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

    for doc_id in req.doc_ids:
        if not db.get(DocumentAsset, doc_id):
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    job = DeckJob(
        id=str(uuid4()),
        job_type="outline",
        status="queued",
        phase="queued",
        progress_pct=0,
        payload_json=req.model_dump_json(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    run_outline_job.delay(job.id)
    return job


@app.get(f"{settings.api_prefix}/decks/outline/{{job_id}}", response_model=OutlineResultOut)
def get_outline(job_id: str, db: Session = Depends(get_db)):
    job = db.get(DeckJob, job_id)
    if not job or job.job_type != "outline":
        raise HTTPException(status_code=404, detail="Outline job not found")

    row = db.scalar(select(DeckOutline).where(DeckOutline.job_id == job_id))
    if not row:
        return OutlineResultOut(job_id=job_id, status=job.status)

    payload = read_json(Path(row.outline_json_path)) if Path(row.outline_json_path).exists() else {}
    return OutlineResultOut(
        job_id=job_id,
        status=job.status,
        prompt=row.prompt,
        thesis=payload.get("thesis"),
        slides=payload.get("slides", []),
    )


@app.post(f"{settings.api_prefix}/decks/{{deck_id}}/revise", response_model=JobOut)
def revise_deck(deck_id: str, req: ReviseDeckRequest, db: Session = Depends(get_db)):
    deck = db.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    payload = {"deck_id": deck_id, **req.model_dump()}
    job = DeckJob(
        id=str(uuid4()),
        job_type="revise",
        status="queued",
        phase="queued",
        progress_pct=0,
        deck_id=deck_id,
        payload_json=json.dumps(payload),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    run_revision_job.delay(job.id)
    return job


@app.get(f"{settings.api_prefix}/jobs/{{job_id}}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(DeckJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get(f"{settings.api_prefix}/jobs/{{job_id}}/events", response_model=list[JobEventOut])
def get_job_events(
    job_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    job = db.get(DeckJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    rows = db.scalars(
        select(JobEvent)
        .where(JobEvent.job_id == job_id)
        .order_by(JobEvent.ts.asc(), JobEvent.id.asc())
        .limit(limit)
    ).all()
    return [
        JobEventOut(
            id=row.id,
            job_id=row.job_id,
            ts=row.ts,
            stage=row.stage,
            event_type=row.event_type,
            payload=decode_payload(row.payload_json),
            severity=row.severity,
        )
        for row in rows
    ]


@app.get(f"{settings.api_prefix}/decks", response_model=list[DeckOut])
def list_decks(db: Session = Depends(get_db)):
    return db.scalars(select(Deck).order_by(Deck.updated_at.desc())).all()


@app.get(f"{settings.api_prefix}/decks/{{deck_id}}", response_model=DeckDetailOut)
def get_deck(deck_id: str, db: Session = Depends(get_db)):
    deck = db.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    versions = db.scalars(
        select(DeckVersion).where(DeckVersion.deck_id == deck_id).order_by(DeckVersion.version.desc())
    ).all()

    return DeckDetailOut(
        id=deck.id,
        template_id=deck.template_id,
        latest_version=deck.latest_version,
        created_at=deck.created_at,
        updated_at=deck.updated_at,
        versions=[
            {
                "version": v.version,
                "prompt": v.prompt,
                "created_at": v.created_at,
                "is_manual_edit": bool(v.is_manual_edit),
                "warnings": (
                    read_json(Path(v.content_json_path)).get("quality_report", {}).get("warnings", [])
                    if Path(v.content_json_path).exists()
                    else []
                ),
            }
            for v in versions
        ],
    )


@app.get(f"{settings.api_prefix}/decks/{{deck_id}}/download")
def download_deck(deck_id: str, version: int | None = Query(default=None), db: Session = Depends(get_db)):
    deck = db.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    version_num = version or deck.latest_version
    row = db.scalar(select(DeckVersion).where(DeckVersion.deck_id == deck_id, DeckVersion.version == version_num))
    if not row:
        raise HTTPException(status_code=404, detail="Deck version not found")

    path = Path(row.pptx_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Deck file not found")

    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", filename=path.name)


@app.get(f"{settings.api_prefix}/decks/{{deck_id}}/quality/{{version}}", response_model=QualityReportOut)
def get_quality_report(deck_id: str, version: int, db: Session = Depends(get_db)):
    deck = db.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    row = db.scalar(
        select(QualityReport).where(
            QualityReport.deck_id == deck_id,
            QualityReport.version == version,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Quality report not found")

    return QualityReportOut(
        deck_id=deck_id,
        version=version,
        score=row.score,
        passes_used=row.passes_used,
        issues=decode_payload(row.issues_json),
        created_at=row.created_at,
    )


@app.post(f"{settings.api_prefix}/search", response_model=list[SearchResult])
def search(req: SearchRequest):
    rows = search_web(req.query, req.max_results)
    return [SearchResult(**{k: row[k] for k in ["source_id", "title", "url", "snippet"]}) for row in rows]


@app.post(f"{settings.api_prefix}/demo/json-render/query", response_model=JsonRenderDemoQueryOut)
def query_json_render_demo(req: JsonRenderDemoQueryRequest, db: Session = Depends(get_db)):
    if req.agentic:
        result = run_agentic_json_render_query(
            db,
            query=req.query,
            max_points=req.max_points,
            provider_name=req.provider,
        )
    else:
        result = run_json_render_demo_query(db, query=req.query, max_points=req.max_points)
    return JsonRenderDemoQueryOut(**result)


@app.post(f"{settings.api_prefix}/editor/session", response_model=EditorSessionOut)
def editor_session(req: EditorSessionRequest, db: Session = Depends(get_db)):
    deck = db.get(Deck, req.deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    config = build_editor_config(deck.id, deck.latest_version)
    return EditorSessionOut(config=config)


@app.post(f"{settings.api_prefix}/editor/callback")
def editor_callback(payload: EditorCallbackPayload, deck_id: str = Query(...), db: Session = Depends(get_db)):
    deck = db.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    if payload.status == 2 and payload.url:
        response = requests.get(payload.url, timeout=30)
        response.raise_for_status()

        latest = db.scalar(select(DeckVersion).where(DeckVersion.deck_id == deck_id, DeckVersion.version == deck.latest_version))
        if not latest:
            raise HTTPException(status_code=404, detail="Latest deck version not found")

        next_version = deck.latest_version + 1
        output_path = make_file_path("outputs", "pptx", stem=f"{deck.id}-v{next_version}")
        output_path.write_bytes(response.content)

        citations_path = make_file_path("citations", "json", stem=f"{deck.id}-v{next_version}-citations")
        write_json(citations_path, {"sources": [], "assets": [], "note": "Manual edit via editor callback"})

        content_path = make_file_path("manifests", "json", stem=f"{deck.id}-v{next_version}-content")
        if Path(latest.content_json_path).exists():
            original_content = read_json(Path(latest.content_json_path))
        else:
            original_content = {"slides": []}
        write_json(content_path, original_content)

        row = DeckVersion(
            deck_id=deck.id,
            version=next_version,
            prompt="Manual editor save",
            content_json_path=str(content_path),
            pptx_path=str(output_path),
            source_manifest_path=str(citations_path),
            is_manual_edit=1,
        )
        db.add(row)
        deck.latest_version = next_version
        deck.updated_at = datetime.utcnow()
        db.add(deck)
        db.commit()

    return {"error": 0}
