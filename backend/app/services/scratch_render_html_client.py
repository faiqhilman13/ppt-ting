from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

from app.config import settings
from app.providers.base import BaseLLMProvider
from app.services.scratch_html_spec_service import (
    build_scratch_html_spec,
    repair_scratch_html_spec_locally,
    repair_scratch_html_spec_with_llm,
    resolve_scratch_html_spec,
)
from app.services.scratch_render_client import render_scratch_pptx


logger = logging.getLogger(__name__)


def _extract_renderer_error(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("error") or payload.get("detail")
        if detail:
            return str(detail)
    text = (resp.text or "").strip()
    if text:
        return text
    return f"HTTP {resp.status_code} from scratch-renderer /render-html"


def _preview(text: str, limit: int = 300) -> str:
    raw = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(raw) <= limit:
        return raw
    return raw[:limit].rstrip() + " ..."


def render_scratch_html_pptx(
    *,
    slides_payload: list[dict],
    output_path: Path,
    title: str,
    theme: str | dict = "default",
    html_spec: dict[str, Any] | None = None,
    provider: BaseLLMProvider | None = None,
    deck_prompt: str | None = None,
) -> dict[str, Any]:
    effective_html_spec, html_spec_meta = resolve_scratch_html_spec(
        slides_payload=slides_payload,
        title=title,
        theme=theme,
        requested_html_spec=html_spec,
        provider=provider,
        deck_prompt=deck_prompt,
    )

    repair_attempts = 0
    repair_budget = max(0, int(settings.scratch_html_spec_repair_attempts))
    local_repair_attempts = 0
    local_repair_budget = max(0, int(settings.scratch_html_spec_local_repair_attempts))
    template_recovery_used = False
    last_renderer_error = ""

    while True:
        payload = {
            "slides": slides_payload,
            "title": title,
            "theme": theme,
            "outputPath": str(output_path),
            "htmlSpec": effective_html_spec,
        }

        try:
            resp = requests.post(
                f"{settings.scratch_renderer_url}/render-html",
                json=payload,
                timeout=120,
            )
            if resp.ok:
                response_json = resp.json() if resp.content else {}
                logger.info("scratch-renderer(html) produced %s", output_path)
                return {
                    "engine": "scratch_html",
                    "fallback": False,
                    "html_spec_source": html_spec_meta.get("source"),
                    "html_spec_strategy": html_spec_meta.get("strategy"),
                    "html_slide_count": len(effective_html_spec.get("slides") or []),
                    "html_spec_skill_doc_path": html_spec_meta.get("skill_doc_path"),
                    "html_spec_script_path": html_spec_meta.get("html2pptx_script_path"),
                    "html_spec_sanitized_slide_count": html_spec_meta.get("sanitized_slide_count"),
                    "html_spec_sanitize_changes": html_spec_meta.get("sanitize_changes"),
                    "html2pptx_source": response_json.get("html2pptxSource"),
                    "html2pptx_path": response_json.get("html2pptxPath"),
                    "repair_attempts": repair_attempts,
                    "local_repair_attempts": local_repair_attempts,
                    "template_recovery_used": template_recovery_used,
                }
            last_renderer_error = _extract_renderer_error(resp)
        except Exception as exc:
            last_renderer_error = str(exc)

        logger.warning(
            "scratch-renderer(html) failed source=%s strategy=%s repair_attempts=%d error=%s",
            html_spec_meta.get("source"),
            html_spec_meta.get("strategy"),
            repair_attempts,
            _preview(last_renderer_error),
        )

        if local_repair_attempts < local_repair_budget:
            repaired_spec, repaired_meta = repair_scratch_html_spec_locally(
                current_html_spec=effective_html_spec,
                validation_error=last_renderer_error,
            )
            if repaired_spec is not None:
                local_repair_attempts += 1
                effective_html_spec = repaired_spec
                html_spec_meta = {
                    **html_spec_meta,
                    **repaired_meta,
                    "skill_doc_path": html_spec_meta.get("skill_doc_path"),
                    "html2pptx_script_path": html_spec_meta.get("html2pptx_script_path"),
                }
                logger.info(
                    "scratch_html_spec_local_repair_applied attempt=%d source=%s",
                    local_repair_attempts,
                    html_spec_meta.get("source"),
                )
                continue

        if provider and repair_attempts < repair_budget:
            repaired_spec, repaired_meta = repair_scratch_html_spec_with_llm(
                provider=provider,
                current_html_spec=effective_html_spec,
                slides_payload=slides_payload,
                title=title,
                theme=theme,
                deck_prompt=deck_prompt or title,
                validation_error=last_renderer_error,
            )
            repair_attempts += 1
            if repaired_spec is not None:
                effective_html_spec = repaired_spec
                html_spec_meta = repaired_meta
                logger.info(
                    "scratch_html_spec_repair_applied attempt=%d source=%s",
                    repair_attempts,
                    html_spec_meta.get("source"),
                )
                continue
            logger.warning(
                "scratch_html_spec_repair_failed attempt=%d reason=%s",
                repair_attempts,
                repaired_meta.get("reason"),
            )

        if not template_recovery_used and html_spec_meta.get("strategy") != "template_builder":
            effective_html_spec = build_scratch_html_spec(
                slides_payload=slides_payload,
                title=title,
                theme=theme,
            )
            html_spec_meta = {
                "source": "auto_generated_recovery",
                "strategy": "template_builder",
                "slide_count": len(effective_html_spec.get("slides") or []),
                "skill_doc_path": html_spec_meta.get("skill_doc_path"),
                "html2pptx_script_path": html_spec_meta.get("html2pptx_script_path"),
            }
            template_recovery_used = True
            logger.warning("scratch_html_spec_recovered_with_template_builder")
            continue

        break

    if settings.pptx_skill_strict:
        logger.error(
            "scratch-renderer html engine failed in strict mode after retries/recovery: %s",
            _preview(last_renderer_error),
        )
        raise RuntimeError(last_renderer_error or "scratch html render failed in strict mode")

    logger.warning("scratch-renderer html engine failed, falling back to native scratch renderer")
    render_scratch_pptx(
        slides_payload=slides_payload,
        output_path=output_path,
        title=title,
        theme=theme,
    )
    return {
        "engine": "scratch_native",
        "fallback": True,
        "reason": last_renderer_error,
        "html_spec_source": html_spec_meta.get("source"),
        "html_spec_strategy": html_spec_meta.get("strategy"),
        "html_slide_count": len(effective_html_spec.get("slides") or []),
        "html_spec_skill_doc_path": html_spec_meta.get("skill_doc_path"),
        "html_spec_script_path": html_spec_meta.get("html2pptx_script_path"),
        "html_spec_sanitized_slide_count": html_spec_meta.get("sanitized_slide_count"),
        "html_spec_sanitize_changes": html_spec_meta.get("sanitize_changes"),
        "repair_attempts": repair_attempts,
        "local_repair_attempts": local_repair_attempts,
        "template_recovery_used": template_recovery_used,
        "last_renderer_error": _preview(last_renderer_error, 1200),
    }
