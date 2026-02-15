from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import Deck, DeckJob, DeckVersion, DocumentAsset, Template
from app.providers.factory import get_provider
from app.services.content_quality import validate_and_rewrite_slides
from app.services.research_service import combine_research
from app.services.render_client import render_pptx
from app.storage import make_file_path, read_json, write_json


def _set_job_state(db, job: DeckJob, *, status: str, phase: str, progress: int, error_code=None, error_message=None):
    job.status = status
    job.phase = phase
    job.progress_pct = progress
    job.error_code = error_code
    job.error_message = error_message
    job.updated_at = datetime.utcnow()
    if status in {"completed", "failed"}:
        job.completed_at = datetime.utcnow()
    db.add(job)
    db.commit()


def _load_doc_chunks(db, doc_ids: list[str]) -> list[dict]:
    chunks: list[dict] = []
    if not doc_ids:
        return chunks

    rows = db.scalars(select(DocumentAsset).where(DocumentAsset.id.in_(doc_ids))).all()
    for row in rows:
        text = Path(row.extracted_text_path).read_text(encoding="utf-8", errors="ignore")
        excerpt = text[:1200]
        chunks.append(
            {
                "source_id": f"doc-{row.id}",
                "title": row.filename,
                "url": f"local://{row.id}",
                "snippet": excerpt[:220],
                "excerpt": excerpt,
                "retrieved_at": datetime.utcnow().isoformat(),
            }
        )
    return chunks


def _serialize_slide_content(slides) -> list[dict]:
    return [
        {
            "template_slide_index": slide.template_slide_index,
            "slots": slide.slots,
        }
        for slide in slides
    ]


@celery_app.task(name="app.tasks.run_generation_job")
def run_generation_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(DeckJob, job_id)
        if not job:
            return

        payload = json.loads(job.payload_json)
        _set_job_state(db, job, status="running", phase="research", progress=15)

        prompt = payload["prompt"]
        template_id = payload["template_id"]
        doc_ids = payload.get("doc_ids", [])
        requested_slide_count = payload.get("slide_count", 20)
        provider_name = payload.get("provider")
        extra_instructions = payload.get("extra_instructions")

        template = db.get(Template, template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        template_manifest = read_json(Path(template.manifest_path))
        template_slides = template_manifest.get("slides", [])
        if not template_slides:
            raise ValueError("Template manifest has no editable slide bindings")

        slide_count = min(requested_slide_count, len(template_slides))

        doc_chunks = _load_doc_chunks(db, doc_ids)
        research_chunks = combine_research(prompt, doc_chunks)

        _set_job_state(db, job, status="running", phase="drafting", progress=45)

        provider = get_provider(provider_name)
        slides = provider.generate_slides(
            prompt=prompt,
            research_chunks=research_chunks,
            template_manifest=template_manifest,
            slide_count=slide_count,
            extra_instructions=extra_instructions,
        )
        slides_payload = _serialize_slide_content(slides)
        slides_payload, quality_report = validate_and_rewrite_slides(
            slides_payload=slides_payload,
            template_manifest=template_manifest,
            prompt=prompt,
            research_chunks=research_chunks,
        )

        _set_job_state(db, job, status="running", phase="rendering", progress=70)

        deck = Deck(id=str(uuid4()), template_id=template_id, latest_version=0)
        db.add(deck)
        db.commit()
        db.refresh(deck)

        version_num = 1
        content_path = make_file_path("manifests", "json", stem=f"{deck.id}-v{version_num}-content")
        citations_path = make_file_path("citations", "json", stem=f"{deck.id}-v{version_num}-citations")
        output_path = make_file_path("outputs", "pptx", stem=f"{deck.id}-v{version_num}")

        write_json(
            content_path,
            {
                "slides": slides_payload,
                "prompt": prompt,
                "quality_report": quality_report,
            },
        )
        write_json(citations_path, {"sources": research_chunks})

        render_pptx(
            deck_id=deck.id,
            version=version_num,
            slides=slides_payload,
            output_path=output_path,
            template_manifest=template_manifest,
            template_path=Path(template.file_path),
            base_pptx_path=None,
        )

        deck.latest_version = version_num
        deck.updated_at = datetime.utcnow()
        db.add(deck)

        version = DeckVersion(
            deck_id=deck.id,
            version=version_num,
            prompt=prompt,
            content_json_path=str(content_path),
            pptx_path=str(output_path),
            source_manifest_path=str(citations_path),
            is_manual_edit=0,
        )
        db.add(version)

        job.deck_id = deck.id
        db.add(job)
        db.commit()

        _set_job_state(db, job, status="completed", phase="completed", progress=100)
    except Exception as exc:
        if "job" in locals() and job:
            _set_job_state(
                db,
                job,
                status="failed",
                phase="failed",
                progress=100,
                error_code="GENERATION_FAILED",
                error_message=str(exc),
            )
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_revision_job")
def run_revision_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(DeckJob, job_id)
        if not job:
            return

        payload = json.loads(job.payload_json)
        _set_job_state(db, job, status="running", phase="loading", progress=15)

        deck_id = payload["deck_id"]
        prompt = payload["prompt"]
        provider_name = payload.get("provider")

        deck = db.get(Deck, deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        latest = db.scalar(
            select(DeckVersion).where(DeckVersion.deck_id == deck_id, DeckVersion.version == deck.latest_version)
        )
        if not latest:
            raise ValueError("No deck version found for revision")

        content = read_json(Path(latest.content_json_path))
        existing_slides = content.get("slides", [])

        template = db.get(Template, deck.template_id)
        if not template:
            raise ValueError("Template for deck not found")
        template_manifest = read_json(Path(template.manifest_path))

        sources = read_json(Path(latest.source_manifest_path)).get("sources", [])
        _set_job_state(db, job, status="running", phase="drafting", progress=45)

        provider = get_provider(provider_name)
        revised = provider.revise_slides(
            prompt=prompt,
            existing_slides=existing_slides,
            research_chunks=sources,
            template_manifest=template_manifest,
        )

        slides_payload = _serialize_slide_content(revised)
        slides_payload, quality_report = validate_and_rewrite_slides(
            slides_payload=slides_payload,
            template_manifest=template_manifest,
            prompt=prompt,
            research_chunks=sources,
        )

        version_num = deck.latest_version + 1
        content_path = make_file_path("manifests", "json", stem=f"{deck.id}-v{version_num}-content")
        citations_path = make_file_path("citations", "json", stem=f"{deck.id}-v{version_num}-citations")
        output_path = make_file_path("outputs", "pptx", stem=f"{deck.id}-v{version_num}")

        write_json(
            content_path,
            {
                "slides": slides_payload,
                "prompt": prompt,
                "quality_report": quality_report,
            },
        )
        write_json(citations_path, {"sources": sources, "revision_prompt": prompt})

        _set_job_state(db, job, status="running", phase="rendering", progress=75)
        render_pptx(
            deck_id=deck.id,
            version=version_num,
            slides=slides_payload,
            output_path=output_path,
            template_manifest=template_manifest,
            template_path=Path(template.file_path),
            base_pptx_path=Path(latest.pptx_path),
        )

        new_version = DeckVersion(
            deck_id=deck.id,
            version=version_num,
            prompt=prompt,
            content_json_path=str(content_path),
            pptx_path=str(output_path),
            source_manifest_path=str(citations_path),
            is_manual_edit=0,
        )
        db.add(new_version)
        deck.latest_version = version_num
        deck.updated_at = datetime.utcnow()
        db.add(deck)

        job.deck_id = deck.id
        db.add(job)
        db.commit()

        _set_job_state(db, job, status="completed", phase="completed", progress=100)
    except Exception as exc:
        if "job" in locals() and job:
            _set_job_state(
                db,
                job,
                status="failed",
                phase="failed",
                progress=100,
                error_code="REVISION_FAILED",
                error_message=str(exc),
            )
        raise
    finally:
        db.close()
