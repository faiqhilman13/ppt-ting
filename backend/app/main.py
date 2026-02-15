from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_db
from app.models import Deck, DeckJob, DeckVersion, DocumentAsset, Template
from app.schemas import (
    DeckDetailOut,
    DeckOut,
    DocumentOut,
    EditorCallbackPayload,
    EditorSessionOut,
    EditorSessionRequest,
    GenerateDeckRequest,
    JobOut,
    ReviseDeckRequest,
    SearchRequest,
    SearchResult,
    TemplateOut,
)
from app.services.doc_extractor import SUPPORTED_EXTENSIONS, extract_text
from app.services.editor_service import build_editor_config
from app.services.research_service import search_web
from app.services.template_service import parse_template_manifest
from app.storage import make_file_path, read_json, write_json
from app.tasks import run_generation_job, run_revision_job

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


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
def list_templates(db: Session = Depends(get_db)):
    return db.scalars(select(Template).order_by(Template.created_at.desc())).all()


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


@app.post(f"{settings.api_prefix}/search", response_model=list[SearchResult])
def search(req: SearchRequest):
    rows = search_web(req.query, req.max_results)
    return [SearchResult(**{k: row[k] for k in ["source_id", "title", "url", "snippet"]}) for row in rows]


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
        write_json(citations_path, {"sources": [], "note": "Manual edit via editor callback"})

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
