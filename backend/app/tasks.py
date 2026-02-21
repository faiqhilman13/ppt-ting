from __future__ import annotations

import json
import logging
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pptx import Presentation
from sqlalchemy import select

from app.celery_app import celery_app
from app.agent.critic import (
    collect_qa_issues,
    correction_targets_from_issues,
    quality_score_breakdown,
    quality_score_from_issues,
    should_run_correction_pass,
)
from app.agent.executor import execute_plan_step
from app.agent.planner import build_generation_plan
from app.config import settings
from app.db import SessionLocal
from app.models import Deck, DeckJob, DeckOutline, DeckVersion, DocumentAsset, Template
from app.providers.factory import get_provider
from app.services.content_quality import validate_and_rewrite_slides
from app.services.job_trace import record_job_event, upsert_quality_report
from app.services.ooxml_service import run_ooxml_roundtrip, run_ooxml_validation_gate
from app.services.research_service import combine_research
from app.services.render_client import render_pptx
from app.services.scratch_render_html_client import render_scratch_html_pptx
from app.services.scratch_render_client import render_scratch_pptx
from app.services.template_replace_service import render_template_with_replace
from app.services.theme_generator import generate_theme_from_description, is_preset
from app.services.template_service import extract_current_slot_values, parse_template_manifest
from app.storage import make_file_path, read_json, write_json
from app.tools.base import ToolContext
from app.tools.runner import ToolRunner
from app.tools import register_builtin_tools


logger = logging.getLogger("ppt_agent.jobs")


def _configure_worker_logging() -> None:
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    logger.setLevel(level)
    logging.getLogger("ppt_agent.providers").setLevel(level)
    if settings.suppress_httpx_info_logs:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("anthropic").setLevel(logging.WARNING)


def _event_stage_from_message(message: str) -> str:
    lower = str(message or "").lower()
    if "outline" in lower:
        return "outline"
    if "research" in lower:
        return "research"
    if "render" in lower:
        return "rendering"
    if "quality" in lower or "qa_" in lower:
        return "quality"
    if "tool" in lower:
        return "tool"
    if "revise" in lower or "revision" in lower:
        return "revision"
    if "slide_generate" in lower or "draft" in lower or "thesis" in lower:
        return "drafting"
    if "state_update" in lower:
        return "state"
    return "job"


def _job_log(job_id: str, message: str, **fields) -> None:
    if job_id and job_id != "n/a":
        try:
            record_job_event(
                job_id=job_id,
                stage=_event_stage_from_message(message),
                event_type=message,
                payload=fields,
                severity="warning" if "warning" in str(message).lower() else "info",
            )
        except Exception:
            # Trace persistence must never break task execution.
            pass

    if not settings.verbose_ai_trace and message not in {"generation_job_start", "outline_job_start", "revision_job_start"}:
        return
    try:
        details = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
            for key, value in fields.items()
            if value is not None
        )
        if details:
            logger.info("job=%s %s | %s", job_id, message, details)
        else:
            logger.info("job=%s %s", job_id, message)
    except Exception:
        # Logging must never break task execution.
        logger.info("job=%s %s | log_error=true", job_id, message)


_configure_worker_logging()
register_builtin_tools()


def _preview_text(text: str | None, limit: int | None = None) -> str:
    raw = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    if not raw:
        return ""
    cap = int(limit or settings.log_preview_chars)
    if len(raw) <= cap:
        return raw
    return raw[:cap].rstrip() + " ..."


def _preview_slots(slots: dict[str, str], max_slots: int = 5) -> dict[str, str]:
    preview: dict[str, str] = {}
    for idx, (key, value) in enumerate((slots or {}).items()):
        if idx >= max_slots:
            break
        preview[str(key)] = _preview_text(str(value))
    return preview


def _outline_preview(outline: dict | None, max_rows: int = 6) -> list[dict]:
    rows = []
    if not isinstance(outline, dict):
        return rows
    for row in (outline.get("slides") or [])[:max_rows]:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "template_slide_index": row.get("template_slide_index"),
                "narrative_role": _preview_text(str(row.get("narrative_role", ""))),
                "key_message": _preview_text(str(row.get("key_message", ""))),
            }
        )
    return rows


def _slide_spec_preview(slides: list[dict], max_rows: int = 8) -> list[dict]:
    preview: list[dict] = []
    for row in (slides or [])[:max_rows]:
        preview.append(
            {
                "index": row.get("index"),
                "archetype": row.get("archetype"),
                "slots": list(row.get("slots", [])),
                "narrative_role": _preview_text(str(row.get("narrative_role", ""))),
                "key_message": _preview_text(str(row.get("key_message", ""))),
            }
        )
    return preview


def _slides_payload_preview(rows: list[dict], max_rows: int = 6) -> list[dict]:
    preview: list[dict] = []
    for row in (rows or [])[:max_rows]:
        preview.append(
            {
                "template_slide_index": row.get("template_slide_index"),
                "slots": _preview_slots({str(k): str(v) for k, v in (row.get("slots") or {}).items()}),
            }
        )
    return preview


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
    _job_log(
        job.id,
        "state_update",
        status=status,
        phase=phase,
        progress=progress,
        error_code=error_code,
    )


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


def _load_template_manifest(template: Template) -> dict:
    template_path = Path(template.file_path)
    manifest_path = Path(template.manifest_path)

    if (template.status or "").startswith("scratch"):
        if manifest_path.exists():
            return read_json(manifest_path)
        return {"version": "scratch_v1", "slides": [], "slide_count": 0, "slot_types": []}

    # Re-parse from source so parser improvements apply to older uploads.
    try:
        manifest = parse_template_manifest(template_path)
        write_json(manifest_path, manifest)
        return manifest
    except Exception:
        if manifest_path.exists():
            return read_json(manifest_path)
        raise


def _serialize_slide_content(slides) -> list[dict]:
    return [
        {
            "template_slide_index": slide.template_slide_index,
            "slots": slide.slots,
        }
        for slide in slides
    ]


def _collect_assets(sources: list[dict]) -> list[dict]:
    assets: list[dict] = []
    seen: set[str] = set()
    for source in sources:
        source_id = str(source.get("source_id", ""))
        for asset in source.get("asset_metadata", []) or []:
            if not isinstance(asset, dict):
                continue
            url = str(asset.get("url") or "").strip()
            if not url:
                continue
            dedupe_key = f"{source_id}:{url}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            assets.append(
                {
                    "source_id": source_id,
                    "asset_type": str(asset.get("asset_type") or "asset"),
                    "url": url,
                    "source": str(asset.get("source") or ""),
                }
            )
    return assets


_SCRATCH_ARCHETYPE_CYCLE = ["executive_summary", "comparison", "timeline", "general"]
_ROLE_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "over",
    "under",
    "your",
    "their",
    "about",
}


def _infer_archetype_from_role(narrative_role: str, key_message: str) -> str:
    text = f"{narrative_role} {key_message}".lower()
    if any(token in text for token in ["agenda", "overview", "contents"]):
        return "agenda"
    if any(token in text for token in ["timeline", "roadmap", "phase", "milestone", "sequence"]):
        return "timeline"
    if any(token in text for token in ["kpi", "metric", "impact", "revenue", "cost", "roi", "performance"]):
        return "kpi"
    if any(token in text for token in ["compare", "comparison", "versus", "vs", "tradeoff", "option"]):
        return "comparison"
    if any(token in text for token in ["quote", "testimonial", "voice"]):
        return "quote"
    if any(token in text for token in ["decision", "next step", "call to action", "close", "closing"]):
        return "closing"
    if any(token in text for token in ["summary", "executive", "key takeaway"]):
        return "executive_summary"
    return "general"


def _build_scratch_manifest(slide_count: int) -> dict:
    slides: list[dict] = []
    for i in range(slide_count):
        if i == 0:
            slots = ["TITLE", "SUBTITLE"]
            archetype = "section_break"
        else:
            slots = ["TITLE", "BULLET_1", "BODY_1", "CITATION"]
            archetype = _SCRATCH_ARCHETYPE_CYCLE[(i - 1) % len(_SCRATCH_ARCHETYPE_CYCLE)]
        slides.append(
            {
                "index": i,
                "name": f"scratch-slide-{i + 1}",
                "slots": slots,
                "archetype": archetype,
                "bindings": [],
            }
        )
    slot_types = sorted({slot for row in slides for slot in row.get("slots", [])})
    return {
        "version": "scratch_v1",
        "slide_count": slide_count,
        "slides": slides,
        "slot_types": slot_types,
    }


def _build_scratch_manifest_from_outline(outline: dict | None, slide_count: int) -> dict:
    by_index: dict[int, dict] = {}
    if outline and isinstance(outline.get("slides"), list):
        for row in outline.get("slides", []):
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("template_slide_index"))
            except Exception:
                continue
            if 0 <= idx < slide_count and idx not in by_index:
                by_index[idx] = row

    slides: list[dict] = []
    for i in range(slide_count):
        if i == 0:
            slots = ["TITLE", "SUBTITLE"]
            archetype = "section_break"
        else:
            slots = ["TITLE", "BULLET_1", "BODY_1", "CITATION"]
            row = by_index.get(i, {})
            archetype = _infer_archetype_from_role(
                str(row.get("narrative_role", "")),
                str(row.get("key_message", "")),
            )
            if archetype == "general":
                archetype = _SCRATCH_ARCHETYPE_CYCLE[(i - 1) % len(_SCRATCH_ARCHETYPE_CYCLE)]

        slides.append(
            {
                "index": i,
                "name": f"scratch-slide-{i + 1}",
                "slots": slots,
                "archetype": archetype,
                "bindings": [],
            }
        )

    slot_types = sorted({slot for row in slides for slot in row.get("slots", [])})
    return {
        "version": "scratch_v1",
        "slide_count": slide_count,
        "slides": slides,
        "slot_types": slot_types,
    }


def _create_scratch_template(db, *, manifest: dict, theme: str) -> Template:
    template_id = str(uuid4())
    template_path = make_file_path("templates", "pptx", stem=f"scratch-{template_id}")
    manifest_path = make_file_path("manifests", "json", stem=f"template-{template_id}")

    Presentation().save(str(template_path))
    write_json(manifest_path, manifest)

    row = Template(
        id=template_id,
        name="Scratch Auto Template",
        file_path=str(template_path),
        manifest_path=str(manifest_path),
        status=f"scratch-auto:{theme}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _provider_warnings(provider) -> list[str]:
    warnings = getattr(provider, "last_warnings", [])
    if not warnings:
        return []
    return [str(row) for row in warnings if str(row).strip()]


def _summarize_warnings(warnings: list[str]) -> str | None:
    if not warnings:
        return None
    capped = warnings[:3]
    suffix = " ..." if len(warnings) > 3 else ""
    return "Warnings: " + " | ".join(capped) + suffix


def _scratch_theme_from_template(template: Template) -> str:
    status = str(template.status or "")
    if ":" in status:
        _, theme = status.split(":", 1)
        if theme.strip():
            return theme.strip()
    return settings.scratch_theme


def _max_correction_passes_for_request(
    *,
    requested: int | None,
    quality_profile: str,
) -> int:
    profile = str(quality_profile or settings.default_quality_profile).lower()
    profile_default = 0 if profile == "fast" else (2 if profile == "high_fidelity" else 1)
    value = profile_default if requested is None else int(max(0, requested))
    return min(value, int(settings.max_correction_passes_server))


def _resolve_render_engine(*, creation_mode: str, requested_engine: str | None) -> str:
    creation = str(creation_mode or "template").lower()
    requested = str(requested_engine or "").strip().lower()
    allowed = {
        "scratch": {"scratch_native", "scratch_html"},
        "template": {"template_renderer", "template_replace", "template_ooxml"},
    }
    default_by_mode = {
        "scratch": "scratch_native",
        "template": "template_renderer",
    }
    if creation not in allowed:
        return "template_renderer"
    if requested in allowed[creation]:
        return requested
    return default_by_mode[creation]


def _normalize_slide_sequence(values: list[int] | None) -> list[int]:
    seq: list[int] = []
    for raw in values or []:
        try:
            idx = int(raw)
        except Exception:
            continue
        if idx < 0:
            continue
        seq.append(idx)
    return seq


def _default_template_slide_sequence(template_manifest: dict) -> list[int]:
    out: list[int] = []
    for row in template_manifest.get("slides", []) or []:
        try:
            idx = int(row.get("index"))
        except Exception:
            continue
        if idx < 0:
            continue
        out.append(idx)
    return out


def _maybe_run_template_validation_gate(
    *,
    job_id: str,
    output_path: Path,
    template_path: Path,
) -> dict:
    mode = str(settings.pptx_ooxml_validate_mode or "off").strip().lower()
    if mode not in {"monitor", "enforce"}:
        return {"enabled": False}

    try:
        validation = run_ooxml_validation_gate(
            pptx_path=output_path,
            original_pptx_path=template_path,
        )
        _job_log(
            job_id,
            "ooxml_validate_complete",
            validation_ok=bool(validation.get("ok", False)),
            stdout_preview=_preview_text(validation.get("stdout")),
            stderr_preview=_preview_text(validation.get("stderr")),
            mode=mode,
        )
        if not bool(validation.get("ok", False)) and (mode == "enforce" or settings.pptx_ooxml_fail_closed):
            raise RuntimeError("OOXML validation failed in enforce mode")
        return {"enabled": True, **validation}
    except FileNotFoundError as exc:
        _job_log(job_id, "ooxml_validation_skipped", reason=str(exc))
        return {"enabled": False, "skipped": True, "reason": str(exc)}
    except Exception as exc:
        if mode == "enforce" or settings.pptx_ooxml_fail_closed:
            raise
        _job_log(job_id, "ooxml_validation_warning", reason=str(exc), mode=mode)
        return {"enabled": True, "ok": False, "reason": str(exc)}


def _render_with_engine(
    *,
    job_id: str,
    creation_mode: str,
    render_engine: str,
    slides_payload: list[dict],
    output_path: Path,
    title: str,
    theme: str | dict | None,
    html_spec: dict | None,
    deck_id: str,
    version_num: int,
    template_manifest: dict,
    template_path: Path,
    base_pptx_path: Path | None,
    slide_sequence: list[int],
    ooxml_patch_mode: str | None,
    provider=None,
    deck_prompt: str | None = None,
) -> tuple[str, dict]:
    mode = str(creation_mode or "template").lower()
    engine = _resolve_render_engine(creation_mode=mode, requested_engine=render_engine)
    details: dict = {"requested_engine": render_engine, "resolved_engine": engine}

    if mode == "scratch":
        if engine == "scratch_html":
            _job_log(job_id, "html_render_start", slide_count=len(slides_payload))
            render_meta = render_scratch_html_pptx(
                slides_payload=slides_payload,
                output_path=output_path,
                title=title,
                theme=theme or settings.scratch_theme,
                html_spec=html_spec or {},
                provider=provider,
                deck_prompt=deck_prompt,
            )
            details["html_render"] = render_meta
            _job_log(
                job_id,
                "html_spec_ready",
                source=render_meta.get("html_spec_source"),
                strategy=render_meta.get("html_spec_strategy"),
                html_slide_count=render_meta.get("html_slide_count"),
                skill_doc_path=_preview_text(render_meta.get("html_spec_skill_doc_path")),
                skill_script_path=_preview_text(render_meta.get("html_spec_script_path")),
                html2pptx_source=render_meta.get("html2pptx_source"),
                html2pptx_path=_preview_text(render_meta.get("html2pptx_path")),
                sanitized_slide_count=render_meta.get("html_spec_sanitized_slide_count"),
                sanitize_changes=render_meta.get("html_spec_sanitize_changes"),
                repair_attempts=render_meta.get("repair_attempts"),
                local_repair_attempts=render_meta.get("local_repair_attempts"),
                template_recovery_used=render_meta.get("template_recovery_used"),
                last_renderer_error=_preview_text(render_meta.get("last_renderer_error")),
            )
            if render_meta.get("fallback"):
                _job_log(job_id, "html_render_fallback", reason=render_meta.get("reason"))
                return "scratch_native", details
            _job_log(job_id, "html_render_complete", slide_count=len(slides_payload))
            return "scratch_html", details

        render_scratch_pptx(
            slides_payload=slides_payload,
            output_path=output_path,
            title=title,
            theme=theme or settings.scratch_theme,
        )
        return "scratch_native", details

    if engine == "template_replace":
        _job_log(
            job_id,
            "template_replace_inventory_start",
            slide_sequence=slide_sequence,
            slide_count=len(slides_payload),
        )
        try:
            replace_meta = render_template_with_replace(
                source_pptx_path=base_pptx_path or template_path,
                output_path=output_path,
                slides_payload=slides_payload,
                template_manifest=template_manifest,
                slide_sequence=slide_sequence,
            )
            details["template_replace"] = replace_meta
            _job_log(
                job_id,
                "template_replace_apply_complete",
                replaced_slots=replace_meta.get("replaced_slots"),
                issue_count=replace_meta.get("issue_count"),
            )
            if int(replace_meta.get("issue_count") or 0) > 0:
                _job_log(
                    job_id,
                    "template_replace_issues_detected",
                    issue_count=replace_meta.get("issue_count"),
                )
            details["validation_gate"] = _maybe_run_template_validation_gate(
                job_id=job_id,
                output_path=output_path,
                template_path=template_path,
            )
            return "template_replace", details
        except Exception as exc:
            _job_log(job_id, "template_replace_fallback", reason=str(exc))
            render_pptx(
                deck_id=deck_id,
                version=version_num,
                slides=slides_payload,
                output_path=output_path,
                template_manifest=template_manifest,
                template_path=template_path,
                base_pptx_path=base_pptx_path,
            )
            details["fallback_reason"] = str(exc)
            details["validation_gate"] = _maybe_run_template_validation_gate(
                job_id=job_id,
                output_path=output_path,
                template_path=template_path,
            )
            return "template_renderer", details

    if engine == "template_ooxml":
        base_render_path = output_path.with_name(f"{output_path.stem}-renderer-base{output_path.suffix}")
        render_pptx(
            deck_id=deck_id,
            version=version_num,
            slides=slides_payload,
            output_path=base_render_path,
            template_manifest=template_manifest,
            template_path=template_path,
            base_pptx_path=base_pptx_path,
        )
        _job_log(job_id, "ooxml_unpack_start", patch_mode=ooxml_patch_mode or "none")
        try:
            ooxml_meta = run_ooxml_roundtrip(
                source_pptx_path=base_render_path,
                output_path=output_path,
                original_pptx_path=template_path,
                patch_mode=ooxml_patch_mode or "none",
            )
            details["template_ooxml"] = ooxml_meta
            _job_log(
                job_id,
                "ooxml_pack_complete",
                patch_mode=ooxml_meta.get("patch_mode"),
                patch_applied=ooxml_meta.get("patch_applied"),
            )
            _job_log(
                job_id,
                "ooxml_validate_complete",
                validation_ok=ooxml_meta.get("validation_ok"),
                stdout_preview=_preview_text(ooxml_meta.get("validation_stdout")),
                stderr_preview=_preview_text(ooxml_meta.get("validation_stderr")),
            )
            if not bool(ooxml_meta.get("validation_ok", False)) and settings.pptx_ooxml_fail_closed:
                raise RuntimeError("OOXML roundtrip validation failed with fail-closed mode enabled")
            return "template_ooxml", details
        except Exception as exc:
            _job_log(job_id, "ooxml_fallback", reason=str(exc))
            if base_render_path.exists():
                shutil.copy2(base_render_path, output_path)
            details["fallback_reason"] = str(exc)
            details["validation_gate"] = _maybe_run_template_validation_gate(
                job_id=job_id,
                output_path=output_path,
                template_path=template_path,
            )
            return "template_renderer", details
        finally:
            try:
                if base_render_path.exists():
                    base_render_path.unlink()
            except OSError:
                pass

    render_pptx(
        deck_id=deck_id,
        version=version_num,
        slides=slides_payload,
        output_path=output_path,
        template_manifest=template_manifest,
        template_path=template_path,
        base_pptx_path=base_pptx_path,
    )
    details["validation_gate"] = _maybe_run_template_validation_gate(
        job_id=job_id,
        output_path=output_path,
        template_path=template_path,
    )
    return "template_renderer", details


def _run_research_routing_tool(
    *,
    job_id: str,
    runner: ToolRunner,
    quality_profile: str,
    slide_spec: dict,
    research_chunks: list[dict],
) -> list[dict]:
    result = execute_plan_step(
        runner=runner,
        ctx=ToolContext(job_id=job_id, quality_profile=quality_profile, timeout_seconds=settings.max_tool_runtime_seconds),
        step={"tool": "research.route_sources", "stage": "research"},
        tool_input={
            "slide_spec": slide_spec,
            "research_chunks": research_chunks,
            "max_per_slide": 3,
        },
    )
    chunks = ((result.get("payload") or {}).get("chunks") if isinstance(result, dict) else None) or []
    if isinstance(chunks, list) and chunks:
        return chunks
    return _route_research(slide_spec, research_chunks)


def _run_qa_tools(
    *,
    job_id: str,
    runner: ToolRunner,
    quality_profile: str,
    slides_payload: list[dict],
    template_manifest: dict,
) -> tuple[list[dict], dict]:
    tool_outputs: dict[str, dict] = {}
    content_output = execute_plan_step(
        runner=runner,
        ctx=ToolContext(job_id=job_id, quality_profile=quality_profile, timeout_seconds=settings.max_tool_runtime_seconds),
        step={"tool": "qa.content_check", "stage": "quality"},
        tool_input={"slides_payload": slides_payload, "template_manifest": template_manifest},
    )
    tool_outputs["qa.content_check"] = content_output

    if str(quality_profile).lower() != "fast":
        visual_output = execute_plan_step(
            runner=runner,
            ctx=ToolContext(job_id=job_id, quality_profile=quality_profile, timeout_seconds=settings.max_tool_runtime_seconds),
            step={"tool": "qa.visual_check", "stage": "quality"},
            tool_input={"slides_payload": slides_payload, "template_manifest": template_manifest},
        )
        tool_outputs["qa.visual_check"] = visual_output

    issues = collect_qa_issues(*tool_outputs.values())
    return issues, tool_outputs


def _run_targeted_correction_pass(
    *,
    job_id: str,
    provider_name: str | None,
    prompt: str,
    deck_thesis: str | None,
    selected_slides: list[dict],
    slides_payload: list[dict],
    research_chunks: list[dict],
    template_version: str,
    target_indices: list[int],
    quality_profile: str,
    extra_instructions: str | None,
    runner: ToolRunner,
) -> tuple[list[dict], list[str]]:
    by_slide = {int(row.get("index", -1)): row for row in selected_slides}
    by_payload = {int(row.get("template_slide_index", -1)): row for row in slides_payload}

    warnings: list[str] = []
    correction_hint = (
        "Correction pass: tighten content to avoid overflow, keep bullets concise, and maintain citation fidelity."
    )
    scoped_extra = correction_hint if not extra_instructions else f"{extra_instructions}\n{correction_hint}"

    for idx in target_indices:
        slide_spec = by_slide.get(int(idx))
        if not slide_spec:
            continue
        routed = _run_research_routing_tool(
            job_id=job_id,
            runner=runner,
            quality_profile=quality_profile,
            slide_spec=slide_spec,
            research_chunks=research_chunks,
        )
        generated, row_warnings = _generate_single_slide(
            job_id=job_id,
            provider_name=provider_name,
            prompt=prompt,
            deck_thesis=deck_thesis,
            slide_spec=slide_spec,
            research_chunks=routed,
            extra_instructions=scoped_extra,
            template_version=template_version,
        )
        warnings.extend(row_warnings)
        by_payload[int(generated.get("template_slide_index", -1))] = generated
        _job_log(
            job_id,
            "correction_slide_applied",
            slide_index=idx,
            quality_profile=quality_profile,
            slots=_preview_slots({str(k): str(v) for k, v in (generated.get("slots") or {}).items()}),
        )

    ordered: list[dict] = []
    seen: set[int] = set()
    for row in slides_payload:
        idx = int(row.get("template_slide_index", -1))
        if idx in seen:
            continue
        seen.add(idx)
        ordered.append(by_payload.get(idx, row))
    for idx, row in by_payload.items():
        if idx in seen:
            continue
        ordered.append(row)
    return ordered, warnings


def _default_deck_thesis(prompt: str) -> str:
    text = prompt.strip().rstrip(".")
    if not text:
        return "This deck presents a clear recommendation supported by evidence."
    return f"This deck argues that {text}. It builds a clear case and recommendation."


def _generate_deck_thesis(provider_name: str | None, prompt: str) -> tuple[str, list[str]]:
    provider = get_provider(provider_name)
    thesis = provider.generate_text(
        system_prompt=(
            "Given a deck prompt, produce a concise 1-2 sentence thesis. "
            "Focus on argument, business implication, and decision direction."
        ),
        user_prompt=prompt,
        max_tokens=160,
    )
    cleaned = (thesis or "").strip()
    if not cleaned:
        cleaned = _default_deck_thesis(prompt)
    return cleaned, _provider_warnings(provider)


def _fallback_outline(prompt: str, template_manifest: dict, slide_count: int) -> dict:
    slides = []
    for idx, row in enumerate((template_manifest.get("slides") or [])[: max(1, slide_count)], start=1):
        slides.append(
            {
                "template_slide_index": int(row.get("index", idx - 1)),
                "narrative_role": f"Step {idx}: advance the narrative.",
                "key_message": f"Primary takeaway for step {idx}.",
            }
        )
    return {"thesis": _default_deck_thesis(prompt), "slides": slides}


def _generate_outline_for_generation(
    *,
    provider_name: str | None,
    prompt: str,
    template_manifest: dict,
    slide_count: int,
    research_chunks: list[dict],
) -> tuple[dict, list[str]]:
    provider = get_provider(provider_name)
    warnings: list[str] = []
    try:
        raw_outline = provider.generate_outline(
            prompt=prompt,
            template_manifest=template_manifest,
            slide_count=slide_count,
            research_chunks=research_chunks,
        )
        normalized = _normalize_outline(raw_outline, template_manifest, slide_count)
        warnings.extend(_provider_warnings(provider))
        if normalized:
            return normalized, warnings
        warnings.append("Generated outline was invalid; fallback outline was used.")
    except Exception as exc:
        warnings.extend(_provider_warnings(provider))
        warnings.append(f"Outline generation failed; fallback outline was used ({exc}).")
    return _fallback_outline(prompt, template_manifest, slide_count), warnings


def _normalize_outline(outline: dict | None, template_manifest: dict, slide_count: int) -> dict | None:
    if not outline or not isinstance(outline, dict):
        return None

    by_index = {int(row.get("index", i)): row for i, row in enumerate(template_manifest.get("slides", []))}
    requested = outline.get("slides", [])
    if not isinstance(requested, list):
        requested = []

    normalized_slides: list[dict] = []
    seen: set[int] = set()
    for row in requested:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("template_slide_index"))
        except Exception:
            continue
        if idx in seen or idx not in by_index:
            continue
        seen.add(idx)
        normalized_slides.append(
            {
                "template_slide_index": idx,
                "narrative_role": str(row.get("narrative_role") or "").strip(),
                "key_message": str(row.get("key_message") or "").strip(),
            }
        )
        if len(normalized_slides) >= max(1, slide_count):
            break

    thesis = str(outline.get("thesis") or "").strip()
    if not thesis:
        thesis = None

    if not normalized_slides and not thesis:
        return None
    return {"thesis": thesis, "slides": normalized_slides}


def _select_slides(template_manifest: dict, slide_count: int, outline: dict | None) -> list[dict]:
    all_slides = template_manifest.get("slides", []) or []
    if not all_slides:
        return []

    by_index = {int(row.get("index", i)): row for i, row in enumerate(all_slides)}
    selected: list[dict] = []
    selected_indices: set[int] = set()

    if outline and isinstance(outline.get("slides"), list):
        for row in outline["slides"]:
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("template_slide_index"))
            except Exception:
                continue
            base = by_index.get(idx)
            if not base or idx in selected_indices:
                continue
            enriched = dict(base)
            enriched["narrative_role"] = str(row.get("narrative_role") or "").strip()
            enriched["key_message"] = str(row.get("key_message") or "").strip()
            selected.append(enriched)
            selected_indices.add(idx)
            if len(selected) >= max(1, slide_count):
                break

    # If the outline yields too few valid/unique slides, backfill from remaining
    # template slides so we still honor requested slide_count.
    if len(selected) < max(1, slide_count):
        for row in all_slides:
            idx = int(row.get("index", -1))
            if idx in selected_indices:
                continue
            selected.append(dict(row))
            selected_indices.add(idx)
            if len(selected) >= max(1, slide_count):
                break

    return selected


def _build_manifest_for_selected(template_manifest: dict, selected_slides: list[dict]) -> dict:
    slot_types = sorted({slot for row in selected_slides for slot in row.get("slots", [])})
    return {
        **template_manifest,
        "slide_count": len(selected_slides),
        "slides": selected_slides,
        "slot_types": slot_types,
    }


def _extract_keywords(*parts: str) -> set[str]:
    joined = " ".join(part or "" for part in parts).lower()
    words = {token for token in re.findall(r"[a-z]{3,}", joined) if token not in _ROLE_STOPWORDS}
    return words


def _route_research(slide_spec: dict, all_chunks: list[dict], max_per_slide: int = 3) -> list[dict]:
    if not all_chunks:
        return []

    keywords = _extract_keywords(
        str(slide_spec.get("narrative_role", "")),
        str(slide_spec.get("key_message", "")),
        str(slide_spec.get("name", "")),
        str(slide_spec.get("archetype", "")),
    )
    if not keywords:
        return all_chunks[:max_per_slide]

    scored: list[tuple[int, int, dict]] = []
    for idx, chunk in enumerate(all_chunks):
        title = str(chunk.get("title", "")).lower()
        snippet = str(chunk.get("snippet", "")).lower()
        excerpt = str(chunk.get("excerpt", "")).lower()
        haystack = f"{title} {snippet} {excerpt}"
        overlap = sum(1 for keyword in keywords if keyword in haystack)
        scored.append((overlap, -idx, chunk))

    scored.sort(reverse=True)

    selected: list[dict] = []
    seen: set[str] = set()
    for score, _, chunk in scored:
        if score <= 0:
            continue
        source_id = str(chunk.get("source_id", ""))
        if source_id in seen:
            continue
        seen.add(source_id)
        selected.append(chunk)
        if len(selected) >= max_per_slide:
            break

    if len(selected) < max_per_slide:
        for chunk in all_chunks:
            source_id = str(chunk.get("source_id", ""))
            if source_id in seen:
                continue
            seen.add(source_id)
            selected.append(chunk)
            if len(selected) >= max_per_slide:
                break

    return selected


def _fallback_slide_payload(prompt: str, deck_thesis: str | None, slide_spec: dict) -> dict:
    slots = {}
    for idx, slot in enumerate(slide_spec.get("slots", [])):
        if idx == 0:
            slots[slot] = (deck_thesis or prompt)[:240]
        else:
            slots[slot] = f"{slot.replace('_', ' ').title()} content"
    return {"template_slide_index": int(slide_spec.get("index", -1)), "slots": slots}


def _generate_single_slide(
    *,
    job_id: str | None,
    provider_name: str | None,
    prompt: str,
    deck_thesis: str | None,
    slide_spec: dict,
    research_chunks: list[dict],
    extra_instructions: str | None,
    template_version: str,
) -> tuple[dict, list[str]]:
    provider = get_provider(provider_name)
    slide_idx = int(slide_spec.get("index", -1))
    _job_log(
        job_id or "n/a",
        "slide_generate_start",
        slide_index=slide_idx,
        archetype=slide_spec.get("archetype"),
        slot_names=list(slide_spec.get("slots", [])),
        narrative_role=_preview_text(str(slide_spec.get("narrative_role", ""))),
        key_message=_preview_text(str(slide_spec.get("key_message", ""))),
        slot_count=len(slide_spec.get("slots", [])),
        research_chunks=len(research_chunks),
        research_titles=[_preview_text(str(chunk.get("title", "")), 90) for chunk in research_chunks[:3]],
    )
    single_manifest = {
        "version": template_version,
        "slide_count": 1,
        "slides": [slide_spec],
        "slot_types": list(slide_spec.get("slots", [])),
    }
    try:
        rows = provider.generate_slides(
            prompt=prompt,
            research_chunks=research_chunks,
            template_manifest=single_manifest,
            slide_count=1,
            extra_instructions=extra_instructions,
            deck_thesis=deck_thesis,
        )
        if rows:
            first = rows[0]
            row_warnings = _provider_warnings(provider)
            _job_log(
                job_id or "n/a",
                "slide_generate_done",
                slide_index=slide_idx,
                warning_count=len(row_warnings),
                slot_preview=_preview_slots({str(k): str(v) for k, v in (first.slots or {}).items()}),
            )
            return {
                "template_slide_index": int(slide_spec.get("index", first.template_slide_index)),
                "slots": {str(k): str(v) for k, v in (first.slots or {}).items()},
            }, row_warnings
    except Exception as exc:
        warnings = _provider_warnings(provider)
        warnings.append(f"Slide {slide_spec.get('index')} generation failed; fallback used ({exc}).")
        _job_log(job_id or "n/a", "slide_generate_fallback", slide_index=slide_idx, reason=str(exc))
        return _fallback_slide_payload(prompt, deck_thesis, slide_spec), warnings

    warnings = _provider_warnings(provider)
    warnings.append(f"Slide {slide_spec.get('index')} generation returned empty payload; fallback used.")
    _job_log(job_id or "n/a", "slide_generate_empty_fallback", slide_index=slide_idx)
    return _fallback_slide_payload(prompt, deck_thesis, slide_spec), warnings


def _fallback_revision_payload(existing_slide: dict) -> dict:
    return {
        "template_slide_index": int(existing_slide.get("template_slide_index", -1)),
        "slots": {str(k): str(v) for k, v in (existing_slide.get("slots") or {}).items()},
    }


def _revision_slide_spec(template_manifest: dict, existing_slide: dict) -> dict:
    idx = int(existing_slide.get("template_slide_index", -1))
    by_index = {int(slide.get("index", i)): slide for i, slide in enumerate(template_manifest.get("slides", []))}
    spec = by_index.get(idx)
    if spec:
        return spec
    slots = list((existing_slide.get("slots") or {}).keys())
    return {
        "index": idx,
        "name": f"slide-{idx}",
        "slots": slots,
        "archetype": "general",
        "bindings": [],
    }


def _revise_single_slide(
    *,
    job_id: str | None,
    provider_name: str | None,
    prompt: str,
    existing_slide: dict,
    slide_spec: dict,
    research_chunks: list[dict],
    template_version: str,
) -> tuple[dict, list[str]]:
    provider = get_provider(provider_name)
    slide_idx = int(existing_slide.get("template_slide_index", -1))
    _job_log(
        job_id or "n/a",
        "slide_revise_start",
        slide_index=slide_idx,
        slot_count=len((existing_slide.get("slots") or {}).keys()),
        research_chunks=len(research_chunks),
        existing_slot_preview=_preview_slots({str(k): str(v) for k, v in (existing_slide.get("slots") or {}).items()}),
        research_titles=[_preview_text(str(chunk.get("title", "")), 90) for chunk in research_chunks[:3]],
    )
    single_manifest = {
        "version": template_version,
        "slide_count": 1,
        "slides": [slide_spec],
        "slot_types": list(slide_spec.get("slots", [])),
    }

    try:
        rows = provider.revise_slides(
            prompt=prompt,
            existing_slides=[existing_slide],
            research_chunks=research_chunks,
            template_manifest=single_manifest,
        )
        if rows:
            first = rows[0]
            row_warnings = _provider_warnings(provider)
            _job_log(
                job_id or "n/a",
                "slide_revise_done",
                slide_index=slide_idx,
                warning_count=len(row_warnings),
                slot_preview=_preview_slots({str(k): str(v) for k, v in (first.slots or {}).items()}),
            )
            return {
                "template_slide_index": int(existing_slide.get("template_slide_index", first.template_slide_index)),
                "slots": {str(k): str(v) for k, v in (first.slots or {}).items()},
            }, row_warnings
    except Exception as exc:
        warnings = _provider_warnings(provider)
        warnings.append(
            f"Slide {existing_slide.get('template_slide_index')} revision failed; original content kept ({exc})."
        )
        _job_log(job_id or "n/a", "slide_revise_fallback", slide_index=slide_idx, reason=str(exc))
        return _fallback_revision_payload(existing_slide), warnings

    warnings = _provider_warnings(provider)
    warnings.append(
        f"Slide {existing_slide.get('template_slide_index')} revision returned empty payload; original content kept."
    )
    _job_log(job_id or "n/a", "slide_revise_empty_fallback", slide_index=slide_idx)
    return _fallback_revision_payload(existing_slide), warnings


def _generate_slides_parallel(
    *,
    job_id: str,
    provider_name: str | None,
    prompt: str,
    deck_thesis: str | None,
    selected_slides: list[dict],
    research_chunks: list[dict],
    extra_instructions: str | None,
    template_version: str,
    quality_profile: str,
    runner: ToolRunner,
) -> tuple[list[dict], list[str]]:
    if not selected_slides:
        return [], []

    max_workers = min(8, len(selected_slides))
    _job_log(
        job_id,
        "parallel_generation_dispatch",
        slide_count=len(selected_slides),
        max_workers=max_workers,
    )
    results: dict[int, dict] = {}
    warnings: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {}
        for idx, slide_spec in enumerate(selected_slides):
            routed_research = _run_research_routing_tool(
                job_id=job_id,
                runner=runner,
                quality_profile=quality_profile,
                slide_spec=slide_spec,
                research_chunks=research_chunks,
            )
            _job_log(
                job_id,
                "slide_research_route",
                slide_index=slide_spec.get("index", idx),
                selected_sources=[_preview_text(str(chunk.get("title", "")), 90) for chunk in routed_research],
            )
            future = pool.submit(
                _generate_single_slide,
                job_id=job_id,
                provider_name=provider_name,
                prompt=prompt,
                deck_thesis=deck_thesis,
                slide_spec=slide_spec,
                research_chunks=routed_research,
                extra_instructions=extra_instructions,
                template_version=template_version,
            )
            future_map[future] = idx

        for future in as_completed(future_map):
            idx = future_map[future]
            spec = selected_slides[idx]
            try:
                payload, row_warnings = future.result()
                results[idx] = payload
                warnings.extend(row_warnings)
            except Exception as exc:
                results[idx] = _fallback_slide_payload(prompt, deck_thesis, spec)
                warnings.append(f"Slide {spec.get('index')} crashed during parallel generation; fallback used ({exc}).")

    ordered = [results[idx] for idx in range(len(selected_slides))]
    _job_log(job_id, "parallel_generation_complete", produced=len(ordered), warning_count=len(warnings))
    return ordered, warnings


def _revise_slides_parallel(
    *,
    job_id: str,
    provider_name: str | None,
    prompt: str,
    revise_targets: list[dict],
    research_chunks: list[dict],
    template_manifest: dict,
    quality_profile: str,
    runner: ToolRunner,
) -> tuple[list[dict], list[str]]:
    if not revise_targets:
        return [], []

    max_workers = min(8, len(revise_targets))
    _job_log(
        job_id,
        "parallel_revision_dispatch",
        slide_count=len(revise_targets),
        max_workers=max_workers,
    )
    results: dict[int, dict] = {}
    warnings: list[str] = []
    template_version = str(template_manifest.get("version", ""))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {}
        for idx, existing_slide in enumerate(revise_targets):
            slide_spec = _revision_slide_spec(template_manifest, existing_slide)
            routed_research = _run_research_routing_tool(
                job_id=job_id,
                runner=runner,
                quality_profile=quality_profile,
                slide_spec=slide_spec,
                research_chunks=research_chunks,
            )
            _job_log(
                job_id,
                "slide_research_route",
                slide_index=existing_slide.get("template_slide_index", idx),
                selected_sources=[_preview_text(str(chunk.get("title", "")), 90) for chunk in routed_research],
            )
            future = pool.submit(
                _revise_single_slide,
                job_id=job_id,
                provider_name=provider_name,
                prompt=prompt,
                existing_slide=existing_slide,
                slide_spec=slide_spec,
                research_chunks=routed_research,
                template_version=template_version,
            )
            future_map[future] = idx

        for future in as_completed(future_map):
            idx = future_map[future]
            original = revise_targets[idx]
            try:
                payload, row_warnings = future.result()
                results[idx] = payload
                warnings.extend(row_warnings)
            except Exception as exc:
                results[idx] = _fallback_revision_payload(original)
                warnings.append(
                    f"Slide {original.get('template_slide_index')} crashed during parallel revision; original content kept ({exc})."
                )

    ordered = [results[idx] for idx in range(len(revise_targets))]
    _job_log(job_id, "parallel_revision_complete", produced=len(ordered), warning_count=len(warnings))
    return ordered, warnings


def _save_outline_record(db, *, job: DeckJob, prompt: str, outline: dict) -> None:
    path = make_file_path("manifests", "json", stem=f"outline-{job.id}")
    write_json(path, outline)

    row = db.scalar(select(DeckOutline).where(DeckOutline.job_id == job.id))
    if not row:
        row = DeckOutline(job_id=job.id, prompt=prompt, outline_json_path=str(path))
    else:
        row.prompt = prompt
        row.outline_json_path = str(path)
    db.add(row)
    db.commit()


@celery_app.task(name="app.tasks.run_outline_job")
def run_outline_job(job_id: str):
    db = SessionLocal()
    started_at = perf_counter()
    try:
        job = db.get(DeckJob, job_id)
        if not job:
            return

        payload = json.loads(job.payload_json)
        _job_log(
            job.id,
            "outline_job_start",
            provider=payload.get("provider"),
            creation_mode=payload.get("creation_mode"),
            requested_slide_count=payload.get("slide_count"),
            doc_count=len(payload.get("doc_ids", []) or []),
            prompt_preview=_preview_text(payload.get("prompt")),
        )
        _set_job_state(db, job, status="running", phase="research", progress=20)

        prompt = payload["prompt"]
        creation_mode = str(payload.get("creation_mode", "template")).lower()
        template_id = payload.get("template_id")
        requested_slide_count = int(payload.get("slide_count", 20))
        provider_name = payload.get("provider")
        doc_ids = payload.get("doc_ids", [])

        if creation_mode == "scratch":
            template_manifest = _build_scratch_manifest(max(1, requested_slide_count))
        else:
            template = db.get(Template, template_id)
            if not template:
                raise ValueError(f"Template not found: {template_id}")
            template_manifest = _load_template_manifest(template)

        max_slides = len(template_manifest.get("slides", []))
        if max_slides == 0:
            raise ValueError("Template manifest has no editable slides")

        slide_count = max(1, min(requested_slide_count, max_slides))
        doc_chunks = _load_doc_chunks(db, doc_ids)
        research_chunks = combine_research(prompt, doc_chunks)
        _job_log(
            job.id,
            "outline_inputs_ready",
            manifest_slides=max_slides,
            selected_slide_count=slide_count,
            doc_chunks=len(doc_chunks),
            research_chunks=len(research_chunks),
            research_titles=[_preview_text(str(chunk.get("title", "")), 90) for chunk in research_chunks[:6]],
        )

        _set_job_state(db, job, status="running", phase="drafting", progress=65)
        provider = get_provider(provider_name)
        outline = provider.generate_outline(
            prompt=prompt,
            template_manifest=template_manifest,
            slide_count=slide_count,
            research_chunks=research_chunks,
        )
        normalized_outline = _normalize_outline(outline, template_manifest, slide_count) or _fallback_outline(
            prompt, template_manifest, slide_count
        )
        _job_log(
            job.id,
            "outline_generated",
            thesis_present=bool(normalized_outline.get("thesis")),
            outlined_slides=len(normalized_outline.get("slides", [])),
            thesis_preview=_preview_text(normalized_outline.get("thesis")),
            outline_preview=_outline_preview(normalized_outline),
        )

        _save_outline_record(db, job=job, prompt=prompt, outline=normalized_outline)
        warnings = _provider_warnings(provider)
        _set_job_state(
            db,
            job,
            status="completed",
            phase="completed",
            progress=100,
            error_message=_summarize_warnings(warnings),
        )
        _job_log(
            job.id,
            "outline_job_complete",
            duration_sec=f"{perf_counter() - started_at:.2f}",
            warning_count=len(warnings),
        )
    except Exception as exc:
        if "job" in locals() and job:
            _job_log(job.id, "outline_job_failed", reason=str(exc))
            _set_job_state(
                db,
                job,
                status="failed",
                phase="failed",
                progress=100,
                error_code="OUTLINE_FAILED",
                error_message=str(exc),
            )
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_generation_job")
def run_generation_job(job_id: str):
    db = SessionLocal()
    started_at = perf_counter()
    try:
        job = db.get(DeckJob, job_id)
        if not job:
            return

        payload = json.loads(job.payload_json)
        _job_log(
            job.id,
            "generation_job_start",
            provider=payload.get("provider"),
            creation_mode=payload.get("creation_mode"),
            render_engine=payload.get("render_engine"),
            requested_slide_count=payload.get("slide_count"),
            doc_count=len(payload.get("doc_ids", []) or []),
            has_outline=bool(payload.get("outline")),
            prompt_preview=_preview_text(payload.get("prompt")),
            extra_instructions=_preview_text(payload.get("extra_instructions")),
        )
        _set_job_state(db, job, status="running", phase="research", progress=15)

        prompt = payload["prompt"]
        creation_mode = str(payload.get("creation_mode", "template")).lower()
        template_id = payload.get("template_id")
        doc_ids = payload.get("doc_ids", [])
        requested_slide_count = int(payload.get("slide_count", 20))
        provider_name = payload.get("provider")
        provider = get_provider(provider_name)
        render_engine_requested = payload.get("render_engine")
        render_engine = _resolve_render_engine(
            creation_mode=creation_mode,
            requested_engine=render_engine_requested,
        )
        html_spec = payload.get("html_spec") if isinstance(payload.get("html_spec"), dict) else None
        requested_slide_sequence = _normalize_slide_sequence(payload.get("slide_sequence"))
        ooxml_patch_mode = str(payload.get("ooxml_patch_mode") or "none").strip().lower()
        if ooxml_patch_mode not in {"none", "normalize"}:
            ooxml_patch_mode = "none"
        extra_instructions = payload.get("extra_instructions")
        scratch_theme = (payload.get("scratch_theme") or "").strip()
        resolved_theme: str | dict = scratch_theme or settings.scratch_theme
        if creation_mode == "scratch":
            if scratch_theme and is_preset(scratch_theme):
                resolved_theme = scratch_theme
            else:
                style_source = scratch_theme or prompt
                _job_log(job.id, "theme_generation_start", description=_preview_text(style_source))
                resolved_theme = generate_theme_from_description(
                    style_description=style_source,
                    provider_name=provider_name,
                )
                _job_log(
                    job.id,
                    "theme_generation_complete",
                    primary=resolved_theme.get("primary"),
                    accent=resolved_theme.get("accent"),
                    headerFont=resolved_theme.get("headerFont"),
                )
        requested_outline = payload.get("outline")
        agent_mode = str(payload.get("agent_mode") or settings.default_agent_mode).lower()
        if agent_mode not in {"off", "bounded"}:
            agent_mode = settings.default_agent_mode
        quality_profile = str(payload.get("quality_profile") or settings.default_quality_profile).lower()
        if quality_profile not in {"fast", "balanced", "high_fidelity"}:
            quality_profile = settings.default_quality_profile
        max_correction_passes = _max_correction_passes_for_request(
            requested=payload.get("max_correction_passes"),
            quality_profile=quality_profile,
        )
        runner = ToolRunner(default_timeout=settings.max_tool_runtime_seconds)
        _job_log(
            job.id,
            "agent_controls_resolved",
            agent_mode=agent_mode,
            quality_profile=quality_profile,
            max_correction_passes=max_correction_passes,
        )

        if creation_mode == "scratch":
            slide_count = max(1, requested_slide_count)
            template_manifest = _build_scratch_manifest(slide_count)
            template = _create_scratch_template(db, manifest=template_manifest, theme=scratch_theme)
        else:
            template = db.get(Template, template_id)
            if not template:
                raise ValueError(f"Template not found: {template_id}")
            template_manifest = _load_template_manifest(template)
            slide_count = max(1, min(requested_slide_count, len(template_manifest.get("slides", []))))
        _job_log(
            job.id,
            "template_ready",
            template_id=template.id,
            manifest_slides=len(template_manifest.get("slides", [])),
            slide_count=slide_count,
            scratch_theme=scratch_theme if creation_mode == "scratch" else None,
            template_status=getattr(template, "status", None),
        )

        if not template_manifest.get("slides"):
            raise ValueError("Template manifest has no editable slide bindings")

        doc_chunks = _load_doc_chunks(db, doc_ids)
        research_chunks = combine_research(prompt, doc_chunks)
        _job_log(
            job.id,
            "research_ready",
            doc_chunks=len(doc_chunks),
            research_chunks=len(research_chunks),
            research_titles=[_preview_text(str(chunk.get("title", "")), 90) for chunk in research_chunks[:6]],
        )

        outline_warnings: list[str] = []
        outline_source = "provided"
        outline = _normalize_outline(requested_outline, template_manifest, slide_count)
        if outline is None:
            outline_source = "generated"
            outline, generated_outline_warnings = _generate_outline_for_generation(
                provider_name=provider_name,
                prompt=prompt,
                template_manifest=template_manifest,
                slide_count=slide_count,
                research_chunks=research_chunks,
            )
            if requested_outline is not None:
                outline_warnings.append("Provided outline was invalid; generated outline was used.")
            outline_warnings.extend(generated_outline_warnings)
        _job_log(
            job.id,
            "outline_ready_for_generation",
            source=outline_source,
            outlined_slides=len(outline.get("slides", [])),
            thesis_present=bool(outline.get("thesis")),
            warning_count=len(outline_warnings),
            thesis_preview=_preview_text(outline.get("thesis")),
            outline_preview=_outline_preview(outline),
        )

        if creation_mode == "scratch":
            template_manifest = _build_scratch_manifest_from_outline(outline, slide_count)
            write_json(Path(template.manifest_path), template_manifest)
            outline = _normalize_outline(outline, template_manifest, slide_count) or _fallback_outline(
                prompt, template_manifest, slide_count
            )
            _job_log(job.id, "scratch_manifest_aligned_to_outline", slide_count=slide_count)

        selected_slides = _select_slides(template_manifest, slide_count, outline)
        generation_manifest = _build_manifest_for_selected(template_manifest, selected_slides)
        if agent_mode == "bounded":
            plan = build_generation_plan(
                creation_mode=creation_mode,
                quality_profile=quality_profile,
                selected_slides=selected_slides,
            )
            _job_log(
                job.id,
                "agent_plan_ready",
                step_count=len(plan.get("steps", [])),
                plan=plan,
            )
        _job_log(
            job.id,
            "selection_ready",
            selected_slides=len(selected_slides),
            generation_manifest_slides=len(generation_manifest.get("slides", [])),
            selected_slide_plan=_slide_spec_preview(selected_slides),
        )
        slide_sequence = (
            requested_slide_sequence
            if requested_slide_sequence
            else _default_template_slide_sequence(generation_manifest)
        )

        _set_job_state(db, job, status="running", phase="drafting", progress=45)
        thesis_warnings: list[str] = []
        if outline and outline.get("thesis"):
            deck_thesis = str(outline["thesis"]).strip()
        else:
            deck_thesis, thesis_warnings = _generate_deck_thesis(provider_name, prompt)
            if outline is None:
                outline = {"thesis": deck_thesis, "slides": []}
            else:
                outline["thesis"] = deck_thesis
        _job_log(
            job.id,
            "thesis_ready",
            thesis_length=len(deck_thesis),
            thesis_warning_count=len(thesis_warnings),
            thesis_preview=_preview_text(deck_thesis),
        )

        generation_started = perf_counter()
        slides_payload, parallel_warnings = _generate_slides_parallel(
            job_id=job.id,
            provider_name=provider_name,
            prompt=prompt,
            deck_thesis=deck_thesis,
            selected_slides=selected_slides,
            research_chunks=research_chunks,
            extra_instructions=extra_instructions,
            template_version=str(generation_manifest.get("version", "")),
            quality_profile=quality_profile,
            runner=runner,
        )
        _job_log(
            job.id,
            "generation_payload_ready",
            slide_payload_count=len(slides_payload),
            warning_count=len(parallel_warnings),
            duration_sec=f"{perf_counter() - generation_started:.2f}",
            slides_preview=_slides_payload_preview(slides_payload),
        )

        slides_payload, quality_report = validate_and_rewrite_slides(
            slides_payload=slides_payload,
            template_manifest=generation_manifest,
            prompt=prompt,
            research_chunks=research_chunks,
        )
        _job_log(
            job.id,
            "quality_pass_complete",
            rewrites=quality_report.get("rewrites_applied"),
            warnings=len(quality_report.get("warnings", [])),
            warning_preview=[_preview_text(str(w), 140) for w in (quality_report.get("warnings", []) or [])[:8]],
        )
        combined_warnings = quality_report.setdefault("warnings", [])
        combined_warnings.extend(outline_warnings)
        combined_warnings.extend(thesis_warnings)
        combined_warnings.extend(parallel_warnings)
        baseline_warnings = list(combined_warnings)

        qa_issues: list[dict] = []
        qa_tool_outputs: dict[str, dict] = {}
        correction_passes_used = 0

        if agent_mode == "bounded":
            qa_issues, qa_tool_outputs = _run_qa_tools(
                job_id=job.id,
                runner=runner,
                quality_profile=quality_profile,
                slides_payload=slides_payload,
                template_manifest=generation_manifest,
            )
            quality_report["qa_issues"] = qa_issues
            quality_report["qa_tool_outputs"] = qa_tool_outputs
            _job_log(
                job.id,
                "qa_initial_complete",
                issue_count=len(qa_issues),
                critical_count=sum(1 for row in qa_issues if str(row.get("severity", "")).lower() == "critical"),
            )

            while should_run_correction_pass(
                issues=qa_issues,
                passes_used=correction_passes_used,
                max_passes=max_correction_passes,
            ):
                correction_passes_used += 1
                targets = correction_targets_from_issues(qa_issues)
                if not targets:
                    break
                _job_log(
                    job.id,
                    "correction_pass_start",
                    pass_number=correction_passes_used,
                    targets=targets,
                )
                corrected_payload, correction_warnings = _run_targeted_correction_pass(
                    job_id=job.id,
                    provider_name=provider_name,
                    prompt=prompt,
                    deck_thesis=deck_thesis,
                    selected_slides=selected_slides,
                    slides_payload=slides_payload,
                    research_chunks=research_chunks,
                    template_version=str(generation_manifest.get("version", "")),
                    target_indices=targets,
                    quality_profile=quality_profile,
                    runner=runner,
                    extra_instructions=extra_instructions,
                )
                slides_payload, quality_report = validate_and_rewrite_slides(
                    slides_payload=corrected_payload,
                    template_manifest=generation_manifest,
                    prompt=prompt,
                    research_chunks=research_chunks,
                )
                quality_report.setdefault("warnings", []).extend(baseline_warnings)
                quality_report.setdefault("warnings", []).extend(correction_warnings)
                qa_issues, qa_tool_outputs = _run_qa_tools(
                    job_id=job.id,
                    runner=runner,
                    quality_profile=quality_profile,
                    slides_payload=slides_payload,
                    template_manifest=generation_manifest,
                )
                quality_report["qa_issues"] = qa_issues
                quality_report["qa_tool_outputs"] = qa_tool_outputs
                _job_log(
                    job.id,
                    "correction_pass_complete",
                    pass_number=correction_passes_used,
                    issue_count=len(qa_issues),
                )
            quality_report["correction_passes_used"] = correction_passes_used
            score_breakdown = quality_score_breakdown(
                issues=qa_issues,
                warnings=quality_report.get("warnings", []),
                rewrites_applied=int(quality_report.get("rewrites_applied") or 0),
                correction_passes_used=correction_passes_used,
            )
            quality_report["score"] = quality_score_from_issues(
                qa_issues,
                warnings=quality_report.get("warnings", []),
                rewrites_applied=int(quality_report.get("rewrites_applied") or 0),
                correction_passes_used=correction_passes_used,
            )
            quality_report["score_breakdown"] = score_breakdown

        _set_job_state(db, job, status="running", phase="rendering", progress=70)

        deck = Deck(id=str(uuid4()), template_id=template.id, latest_version=0)
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
                "deck_thesis": deck_thesis,
                "outline": outline,
                "quality_report": quality_report,
                "agent_mode": agent_mode,
                "quality_profile": quality_profile,
                "max_correction_passes": max_correction_passes,
                "resolved_theme": resolved_theme if creation_mode == "scratch" else None,
                "render_engine": render_engine_requested,
                "effective_render_engine": render_engine,
                "html_spec": html_spec if creation_mode == "scratch" else None,
                "slide_sequence": slide_sequence if creation_mode == "template" else None,
                "ooxml_patch_mode": ooxml_patch_mode if creation_mode == "template" else None,
            },
        )
        write_json(citations_path, {"sources": research_chunks, "assets": _collect_assets(research_chunks)})
        _job_log(
            job.id,
            "render_engine_selected",
            requested_engine=render_engine_requested,
            resolved_engine=render_engine,
            creation_mode=creation_mode,
        )
        effective_render_engine, render_meta = _render_with_engine(
            job_id=job.id,
            creation_mode=creation_mode,
            render_engine=render_engine,
            slides_payload=slides_payload,
            output_path=output_path,
            title=prompt,
            theme=resolved_theme,
            html_spec=html_spec,
            deck_id=deck.id,
            version_num=version_num,
            template_manifest=generation_manifest,
            template_path=Path(template.file_path),
            base_pptx_path=None,
            slide_sequence=slide_sequence,
            ooxml_patch_mode=ooxml_patch_mode,
            provider=provider,
            deck_prompt=prompt,
        )
        _job_log(
            job.id,
            "render_complete",
            output_path=output_path,
            rendered_slide_count=len(slides_payload),
            effective_render_engine=effective_render_engine,
        )
        content_after_render = read_json(content_path)
        content_after_render["effective_render_engine"] = effective_render_engine
        content_after_render["render_meta"] = render_meta
        write_json(content_path, content_after_render)

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

        upsert_quality_report(
            deck_id=deck.id,
            version=version_num,
            score=quality_report.get("score"),
            issues={
                "qa_issues": quality_report.get("qa_issues", []),
                "warnings": quality_report.get("warnings", []),
                "qa_tool_outputs": quality_report.get("qa_tool_outputs", {}),
                "score_breakdown": quality_report.get("score_breakdown"),
                "rewrites_applied": quality_report.get("rewrites_applied"),
            },
            passes_used=int(quality_report.get("correction_passes_used", correction_passes_used)),
        )

        _set_job_state(
            db,
            job,
            status="completed",
            phase="completed",
            progress=100,
            error_message=_summarize_warnings(quality_report.get("warnings", [])),
        )
        _job_log(
            job.id,
            "generation_job_complete",
            deck_id=deck.id,
            duration_sec=f"{perf_counter() - started_at:.2f}",
            warning_count=len(quality_report.get("warnings", [])),
        )
    except Exception as exc:
        if "job" in locals() and job:
            _job_log(job.id, "generation_job_failed", reason=str(exc))
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
    started_at = perf_counter()
    try:
        job = db.get(DeckJob, job_id)
        if not job:
            return

        payload = json.loads(job.payload_json)
        _job_log(
            job.id,
            "revision_job_start",
            provider=payload.get("provider"),
            render_engine=payload.get("render_engine"),
            requested_indices=len(payload.get("slide_indices") or []),
            prompt_preview=_preview_text(payload.get("prompt")),
        )
        _set_job_state(db, job, status="running", phase="loading", progress=15)

        deck_id = payload["deck_id"]
        prompt = payload["prompt"]
        provider_name = payload.get("provider")
        render_engine_requested = payload.get("render_engine")
        requested_indices = payload.get("slide_indices") or []
        requested_set = {int(idx) for idx in requested_indices if isinstance(idx, int) or str(idx).isdigit()}
        html_spec = payload.get("html_spec") if isinstance(payload.get("html_spec"), dict) else None
        requested_slide_sequence = _normalize_slide_sequence(payload.get("slide_sequence"))
        ooxml_patch_mode = str(payload.get("ooxml_patch_mode") or "none").strip().lower()
        if ooxml_patch_mode not in {"none", "normalize"}:
            ooxml_patch_mode = "none"
        agent_mode = str(payload.get("agent_mode") or settings.default_agent_mode).lower()
        if agent_mode not in {"off", "bounded"}:
            agent_mode = settings.default_agent_mode
        quality_profile = str(payload.get("quality_profile") or settings.default_quality_profile).lower()
        if quality_profile not in {"fast", "balanced", "high_fidelity"}:
            quality_profile = settings.default_quality_profile
        max_correction_passes = _max_correction_passes_for_request(
            requested=payload.get("max_correction_passes"),
            quality_profile=quality_profile,
        )
        runner = ToolRunner(default_timeout=settings.max_tool_runtime_seconds)
        _job_log(
            job.id,
            "revision_agent_controls_resolved",
            agent_mode=agent_mode,
            quality_profile=quality_profile,
            max_correction_passes=max_correction_passes,
        )

        deck = db.get(Deck, deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        latest = db.scalar(
            select(DeckVersion).where(DeckVersion.deck_id == deck_id, DeckVersion.version == deck.latest_version)
        )
        if not latest:
            raise ValueError("No deck version found for revision")

        template = db.get(Template, deck.template_id)
        if not template:
            raise ValueError("Template for deck not found")
        template_manifest = _load_template_manifest(template)

        content = {}
        if Path(latest.content_json_path).exists():
            content = read_json(Path(latest.content_json_path))
            existing_slides = content.get("slides", [])
        else:
            existing_slides = []

        if not existing_slides:
            existing_slides = extract_current_slot_values(Path(latest.pptx_path), template_manifest)

        if requested_set:
            revise_targets = [row for row in existing_slides if int(row.get("template_slide_index", -1)) in requested_set]
            untouched = [row for row in existing_slides if int(row.get("template_slide_index", -1)) not in requested_set]
        else:
            revise_targets = existing_slides
            untouched = []
        sources = read_json(Path(latest.source_manifest_path)).get("sources", [])
        _job_log(
            job.id,
            "revision_scope_ready",
            total_existing=len(existing_slides),
            target_count=len(revise_targets),
            untouched_count=len(untouched),
            source_count=len(sources),
            requested_indices=sorted(requested_set) if requested_set else [],
            target_preview=_slides_payload_preview(revise_targets),
        )

        _set_job_state(db, job, status="running", phase="drafting", progress=45)

        revision_warnings: list[str] = []
        if not revise_targets:
            revised_payload = []
        else:
            revised_payload, parallel_revision_warnings = _revise_slides_parallel(
                job_id=job.id,
                provider_name=provider_name,
                prompt=prompt,
                revise_targets=revise_targets,
                research_chunks=sources,
                template_manifest=template_manifest,
                quality_profile=quality_profile,
                runner=runner,
            )
            revision_warnings.extend(parallel_revision_warnings)
        _job_log(
            job.id,
            "revision_payload_ready",
            revised_count=len(revised_payload),
            warning_count=len(revision_warnings),
            revised_preview=_slides_payload_preview(revised_payload),
        )

        revised_by_index = {int(row.get("template_slide_index", -1)): row for row in revised_payload}

        merged: list[dict] = []
        for row in existing_slides:
            idx = int(row.get("template_slide_index", -1))
            merged.append(revised_by_index.get(idx, row))
        for row in untouched:
            idx = int(row.get("template_slide_index", -1))
            if not any(int(item.get("template_slide_index", -1)) == idx for item in merged):
                merged.append(row)

        slides_payload, quality_report = validate_and_rewrite_slides(
            slides_payload=merged,
            template_manifest=template_manifest,
            prompt=prompt,
            research_chunks=sources,
        )
        _job_log(
            job.id,
            "revision_quality_pass_complete",
            rewrites=quality_report.get("rewrites_applied"),
            warnings=len(quality_report.get("warnings", [])),
            warning_preview=[_preview_text(str(w), 140) for w in (quality_report.get("warnings", []) or [])[:8]],
        )
        if revision_warnings:
            quality_report.setdefault("warnings", []).extend(revision_warnings)
        if requested_set and not revise_targets:
            quality_report.setdefault("warnings", []).append("No matching slide_indices found; deck remained unchanged.")
        baseline_warnings = list(quality_report.get("warnings", []))

        correction_passes_used = 0
        if agent_mode == "bounded":
            qa_issues, qa_tool_outputs = _run_qa_tools(
                job_id=job.id,
                runner=runner,
                quality_profile=quality_profile,
                slides_payload=slides_payload,
                template_manifest=template_manifest,
            )
            quality_report["qa_issues"] = qa_issues
            quality_report["qa_tool_outputs"] = qa_tool_outputs
            _job_log(
                job.id,
                "revision_qa_initial_complete",
                issue_count=len(qa_issues),
                critical_count=sum(1 for row in qa_issues if str(row.get("severity", "")).lower() == "critical"),
            )

            selected_slides = [row for row in (template_manifest.get("slides") or [])]
            while should_run_correction_pass(
                issues=qa_issues,
                passes_used=correction_passes_used,
                max_passes=max_correction_passes,
            ):
                correction_passes_used += 1
                targets = correction_targets_from_issues(qa_issues)
                if not targets:
                    break
                _job_log(
                    job.id,
                    "revision_correction_pass_start",
                    pass_number=correction_passes_used,
                    targets=targets,
                )
                corrected_payload, correction_warnings = _run_targeted_correction_pass(
                    job_id=job.id,
                    provider_name=provider_name,
                    prompt=prompt,
                    deck_thesis=None,
                    selected_slides=selected_slides,
                    slides_payload=slides_payload,
                    research_chunks=sources,
                    template_version=str(template_manifest.get("version", "")),
                    target_indices=targets,
                    quality_profile=quality_profile,
                    runner=runner,
                    extra_instructions="Revision correction pass. Keep existing structure, fix overflow and clarity issues.",
                )
                slides_payload, quality_report = validate_and_rewrite_slides(
                    slides_payload=corrected_payload,
                    template_manifest=template_manifest,
                    prompt=prompt,
                    research_chunks=sources,
                )
                quality_report.setdefault("warnings", []).extend(baseline_warnings)
                quality_report.setdefault("warnings", []).extend(correction_warnings)
                qa_issues, qa_tool_outputs = _run_qa_tools(
                    job_id=job.id,
                    runner=runner,
                    quality_profile=quality_profile,
                    slides_payload=slides_payload,
                    template_manifest=template_manifest,
                )
                quality_report["qa_issues"] = qa_issues
                quality_report["qa_tool_outputs"] = qa_tool_outputs
                _job_log(
                    job.id,
                    "revision_correction_pass_complete",
                    pass_number=correction_passes_used,
                    issue_count=len(qa_issues),
                )

            quality_report["correction_passes_used"] = correction_passes_used
            score_breakdown = quality_score_breakdown(
                issues=qa_issues,
                warnings=quality_report.get("warnings", []),
                rewrites_applied=int(quality_report.get("rewrites_applied") or 0),
                correction_passes_used=correction_passes_used,
            )
            quality_report["score"] = quality_score_from_issues(
                qa_issues,
                warnings=quality_report.get("warnings", []),
                rewrites_applied=int(quality_report.get("rewrites_applied") or 0),
                correction_passes_used=correction_passes_used,
            )
            quality_report["score_breakdown"] = score_breakdown

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
                "agent_mode": agent_mode,
                "quality_profile": quality_profile,
                "max_correction_passes": max_correction_passes,
                "render_engine": render_engine_requested,
                "html_spec": html_spec if (template.status or "").startswith("scratch") else None,
                "slide_sequence": requested_slide_sequence if requested_slide_sequence else None,
                "ooxml_patch_mode": ooxml_patch_mode,
            },
        )
        write_json(
            citations_path,
            {
                "sources": sources,
                "assets": _collect_assets(sources),
                "revision_prompt": prompt,
            },
        )

        _set_job_state(db, job, status="running", phase="rendering", progress=75)
        creation_mode = "scratch" if (template.status or "").startswith("scratch") else "template"
        render_engine = _resolve_render_engine(
            creation_mode=creation_mode,
            requested_engine=render_engine_requested,
        )
        slide_sequence = (
            requested_slide_sequence
            if requested_slide_sequence
            else ([] if creation_mode == "template" else _default_template_slide_sequence(template_manifest))
        )
        _job_log(
            job.id,
            "render_engine_selected",
            requested_engine=render_engine_requested,
            resolved_engine=render_engine,
            creation_mode=creation_mode,
        )
        if (template.status or "").startswith("scratch"):
            revision_theme_raw = _scratch_theme_from_template(template)
            cached_theme = content.get("resolved_theme") if content else None
            if cached_theme and isinstance(cached_theme, dict):
                revision_theme = cached_theme
            elif is_preset(revision_theme_raw):
                revision_theme = revision_theme_raw
            else:
                revision_theme = generate_theme_from_description(
                    style_description=revision_theme_raw or prompt,
                    provider_name=provider_name,
                )
            effective_render_engine, render_meta = _render_with_engine(
                job_id=job.id,
                creation_mode="scratch",
                render_engine=render_engine,
                slides_payload=slides_payload,
                output_path=output_path,
                title=prompt,
                theme=revision_theme,
                html_spec=html_spec,
                deck_id=deck.id,
                version_num=version_num,
                template_manifest=template_manifest,
                template_path=Path(template.file_path),
                base_pptx_path=Path(latest.pptx_path),
                slide_sequence=slide_sequence,
                ooxml_patch_mode=ooxml_patch_mode,
                provider=provider,
                deck_prompt=prompt,
            )
        else:
            effective_render_engine, render_meta = _render_with_engine(
                job_id=job.id,
                creation_mode="template",
                render_engine=render_engine,
                slides_payload=slides_payload,
                output_path=output_path,
                title=prompt,
                theme=None,
                html_spec=html_spec,
                deck_id=deck.id,
                version_num=version_num,
                template_manifest=template_manifest,
                template_path=Path(template.file_path),
                base_pptx_path=Path(latest.pptx_path),
                slide_sequence=slide_sequence,
                ooxml_patch_mode=ooxml_patch_mode,
                provider=provider,
                deck_prompt=prompt,
            )
        _job_log(
            job.id,
            "revision_render_complete",
            output_path=output_path,
            rendered_slide_count=len(slides_payload),
            effective_render_engine=effective_render_engine,
        )
        revised_content = read_json(content_path)
        revised_content["effective_render_engine"] = effective_render_engine
        revised_content["render_meta"] = render_meta
        write_json(content_path, revised_content)

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

        upsert_quality_report(
            deck_id=deck.id,
            version=version_num,
            score=quality_report.get("score"),
            issues={
                "qa_issues": quality_report.get("qa_issues", []),
                "warnings": quality_report.get("warnings", []),
                "qa_tool_outputs": quality_report.get("qa_tool_outputs", {}),
                "score_breakdown": quality_report.get("score_breakdown"),
                "rewrites_applied": quality_report.get("rewrites_applied"),
            },
            passes_used=int(quality_report.get("correction_passes_used", correction_passes_used)),
        )

        _set_job_state(
            db,
            job,
            status="completed",
            phase="completed",
            progress=100,
            error_message=_summarize_warnings(quality_report.get("warnings", [])),
        )
        _job_log(
            job.id,
            "revision_job_complete",
            deck_id=deck.id,
            duration_sec=f"{perf_counter() - started_at:.2f}",
            warning_count=len(quality_report.get("warnings", [])),
        )
    except Exception as exc:
        if "job" in locals() and job:
            _job_log(job.id, "revision_job_failed", reason=str(exc))
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
