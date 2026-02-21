from __future__ import annotations

import html
import json
import logging
import re
from typing import Any

from lxml import html as lxml_html

from app.config import settings
from app.providers.base import BaseLLMProvider
from app.services.pptx_skill_paths import resolve_skill_path


logger = logging.getLogger(__name__)


_DEFAULT_THEME: dict[str, str] = {
    "primary": "1E2761",
    "secondary": "3949AB",
    "accent": "E8B931",
    "background": "F8FAFC",
    "darkBackground": "1E2761",
    "text": "1E293B",
    "textLight": "F8FAFC",
    "muted": "94A3B8",
    "cardFill": "FFFFFF",
    "cardBorder": "E2E8F0",
    "headerFont": "Georgia",
    "bodyFont": "Calibri",
}

_TEXT_SLOT_KEYS = (
    "TITLE",
    "SUBTITLE",
    "BULLET_1",
    "BULLET_2",
    "BULLET",
    "BODY_1",
    "BODY",
    "CITATION",
)

_HEX6_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_TEXT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li"}
_IGNORE_WRAP_TAGS = {"script", "style"}
_CONTAINER_WRAP_TAGS = {"div", "section", "article", "header", "footer", "main", "aside", "span", "body"}
_INLINE_TEXT_TAGS = {"span", "strong", "em", "b", "i", "u", "mark", "small", "a"}
_STYLE_NUMERIC_PROPS = {
    "font-size",
    "line-height",
    "letter-spacing",
    "margin",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "padding",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "gap",
    "row-gap",
    "column-gap",
    "height",
    "max-height",
    "min-height",
    "width",
    "max-width",
    "min-width",
    "border-radius",
}
_PT_VALUE_RE = re.compile(r"(-?\d+(?:\.\d+)?)pt")
_TOOL_ARTIFACT_RE = re.compile(
    r"(<minimax:tool_call.*?>.*?</minimax:tool_call>|<invoke\b.*?>.*?</invoke>|"
    r"\[TOOL_CALL\].*?\[/TOOL_CALL\]|<tool_call>.*?</tool_call>)",
    re.IGNORECASE | re.DOTALL,
)
_TARGET_SLIDE_RE = re.compile(r"slide-(\d+)\.html", re.IGNORECASE)
_CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_TEXT_SELECTOR_RE = re.compile(r"\b(h[1-6]|p|ul|ol|li)\b", re.IGNORECASE)


def resolve_scratch_html_spec(
    *,
    slides_payload: list[dict[str, Any]],
    title: str,
    theme: str | dict[str, Any] | None,
    requested_html_spec: dict[str, Any] | None = None,
    provider: BaseLLMProvider | None = None,
    deck_prompt: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_slide_count = len(slides_payload or [])
    if _is_valid_html_spec(requested_html_spec, expected_slide_count=expected_slide_count):
        sanitized_spec, sanitize_meta = sanitize_scratch_html_spec(requested_html_spec or {})
        return sanitized_spec, {
            "source": "request",
            "strategy": "request",
            "slide_count": expected_slide_count,
            "skill_doc_path": _path_str(resolve_skill_path("html2pptx.md")),
            "html2pptx_script_path": _path_str(resolve_skill_path("scripts/html2pptx.js")),
            "sanitized_slide_count": sanitize_meta.get("slides_sanitized"),
            "sanitize_changes": sanitize_meta.get("changes"),
        }

    mode = str(settings.scratch_html_spec_mode or "llm_then_template").strip().lower()
    if provider and mode in {"llm", "llm_then_template"}:
        llm_spec, llm_meta = _build_html_spec_with_llm(
            provider=provider,
            slides_payload=slides_payload,
            title=title,
            theme=theme,
            deck_prompt=deck_prompt or title,
        )
        if llm_spec is not None:
            return llm_spec, llm_meta
        if mode == "llm":
            logger.warning(
                "scratch_html_spec_llm_only_failed reason=%s",
                llm_meta.get("reason"),
            )

    fallback_spec = build_scratch_html_spec(
        slides_payload=slides_payload,
        title=title,
        theme=theme,
    )
    return fallback_spec, {
        "source": "auto_generated",
        "strategy": "template_builder",
        "slide_count": len(fallback_spec.get("slides") or []),
        "skill_doc_path": _path_str(resolve_skill_path("html2pptx.md")),
        "html2pptx_script_path": _path_str(resolve_skill_path("scripts/html2pptx.js")),
    }


def _build_html_spec_with_llm(
    *,
    provider: BaseLLMProvider,
    slides_payload: list[dict[str, Any]],
    title: str,
    theme: str | dict[str, Any] | None,
    deck_prompt: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    skill_doc_path = resolve_skill_path("html2pptx.md")
    skill_script_path = resolve_skill_path("scripts/html2pptx.js")
    skill_doc_excerpt = _skill_doc_excerpt(skill_doc_path)

    system_prompt = (
        "You generate HTML specs for a PPT renderer that uses html2pptx.js.\n"
        "Return JSON only, no markdown, no comments.\n"
        'Output schema: {"layout":"LAYOUT_16x9","slides":[string,...]}.\n'
        "Hard requirements:\n"
        "- slides length MUST equal requested slide_count.\n"
        "- Each slide must be full HTML with <!doctype html><html>...<body>...</body></html>.\n"
        "- body must be exactly 720pt x 405pt (16:9) and include display:flex.\n"
        "- Keep a visual safe area: minimum 24pt side/top padding and minimum 36pt bottom clearance.\n"
        "- Put ALL visible text inside <p>, <h1>-<h6>, <ul>, or <ol> tags.\n"
        "- Never use manual bullets like -, *, or bullet symbols. Use <ul>/<ol>.\n"
        "- Use only web-safe fonts.\n"
        "- Avoid CSS gradients; use solid colors only.\n"
        "- Do NOT use background-image/url() anywhere.\n"
        "- Borders/shadows are allowed on <div> only, never on text tags.\n"
        "- Use only inline HTML/CSS that html2pptx can convert.\n"
        "- Avoid absolute positioning and transform-based layouts.\n"
        "- Do not include scripts, external CSS, external assets, or tool-call markup.\n"
        "- Preserve slide intent from slots while producing visually rich layouts.\n\n"
        "Follow this local skill guidance exactly:\n"
        f"{skill_doc_excerpt}"
    )

    payload = {
        "task": "build_html_spec_for_scratch_render",
        "deck_prompt": deck_prompt,
        "deck_title": title,
        "slide_count": len(slides_payload or []),
        "theme": _normalize_theme(theme),
        "slides": [
            {
                "index": idx,
                "archetype": str((row or {}).get("archetype") or "general"),
                "slots": _normalize_slots((row or {}).get("slots")),
            }
            for idx, row in enumerate(slides_payload or [])
        ],
        "renderer_contract": {
            "skill_doc_path": _path_str(skill_doc_path),
            "html2pptx_script_path": _path_str(skill_script_path),
            "required_layout": "LAYOUT_16x9",
            "required_body_size": {"width": "720pt", "height": "405pt"},
        },
    }

    try:
        raw = provider.generate_text(
            system_prompt=system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False),
            max_tokens=max(1200, int(settings.scratch_html_spec_max_tokens)),
            retries=max(0, int(settings.scratch_html_spec_retries)),
        )
    except Exception as exc:
        return None, {
            "source": "llm_failed",
            "strategy": "llm",
            "reason": str(exc),
            "skill_doc_path": _path_str(skill_doc_path),
            "html2pptx_script_path": _path_str(skill_script_path),
        }

    parsed = _extract_json_object(raw)
    if not _is_valid_html_spec(parsed, expected_slide_count=len(slides_payload or [])):
        return None, {
            "source": "llm_invalid",
            "strategy": "llm",
            "reason": "invalid_html_spec_json",
            "raw_preview": _preview(raw, 320),
            "skill_doc_path": _path_str(skill_doc_path),
            "html2pptx_script_path": _path_str(skill_script_path),
        }

    normalized = dict(parsed or {})
    normalized["layout"] = str(normalized.get("layout") or "LAYOUT_16x9")
    normalized, sanitize_meta = sanitize_scratch_html_spec(normalized)
    return normalized, {
        "source": "llm",
        "strategy": "llm",
        "slide_count": len(normalized.get("slides") or []),
        "skill_doc_path": _path_str(skill_doc_path),
        "html2pptx_script_path": _path_str(skill_script_path),
        "sanitized_slide_count": sanitize_meta.get("slides_sanitized"),
        "sanitize_changes": sanitize_meta.get("changes"),
    }


def repair_scratch_html_spec_with_llm(
    *,
    provider: BaseLLMProvider,
    current_html_spec: dict[str, Any],
    slides_payload: list[dict[str, Any]],
    title: str,
    theme: str | dict[str, Any] | None,
    deck_prompt: str,
    validation_error: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    skill_doc_path = resolve_skill_path("html2pptx.md")
    skill_script_path = resolve_skill_path("scripts/html2pptx.js")
    skill_doc_excerpt = _skill_doc_excerpt(skill_doc_path)

    system_prompt = (
        "You repair an HTML presentation spec so it passes html2pptx.js validation.\n"
        "Return JSON only, no markdown.\n"
        'Output schema: {"layout":"LAYOUT_16x9","slides":[string,...]}.\n'
        "Repair goals:\n"
        "- Keep slide count exactly unchanged.\n"
        "- Fix ALL reported validator errors.\n"
        "- Body must remain 720pt x 405pt.\n"
        "- Keep minimum 36pt visual clearance at the bottom.\n"
        "- Keep all visible text inside <p>, <h1>-<h6>, <ul>, or <ol>.\n"
        "- Never leave raw text directly inside <div> without wrapping tags.\n"
        "- Do NOT use background-image/url() anywhere.\n"
        "- Borders/shadows are allowed on <div> only, never on text tags.\n"
        "- Avoid absolute positioning and transform-based layouts.\n"
        "- Use only web-safe fonts and supported CSS.\n"
        "- Maintain original slide intent and content semantics.\n\n"
        "Follow this local skill guidance exactly:\n"
        f"{skill_doc_excerpt}"
    )

    payload = {
        "task": "repair_html_spec_for_html2pptx",
        "deck_prompt": deck_prompt,
        "deck_title": title,
        "slide_count": len(slides_payload or []),
        "theme": _normalize_theme(theme),
        "slides": [
            {
                "index": idx,
                "archetype": str((row or {}).get("archetype") or "general"),
                "slots": _normalize_slots((row or {}).get("slots")),
            }
            for idx, row in enumerate(slides_payload or [])
        ],
        "validation_error": str(validation_error or "")[:8000],
        "current_html_spec": current_html_spec,
        "renderer_contract": {
            "skill_doc_path": _path_str(skill_doc_path),
            "html2pptx_script_path": _path_str(skill_script_path),
            "required_layout": "LAYOUT_16x9",
            "required_body_size": {"width": "720pt", "height": "405pt"},
        },
    }

    try:
        raw = provider.generate_text(
            system_prompt=system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False),
            max_tokens=max(1200, int(settings.scratch_html_spec_repair_max_tokens)),
            retries=max(0, int(settings.scratch_html_spec_retries)),
        )
    except Exception as exc:
        return None, {
            "source": "llm_repair_failed",
            "strategy": "llm_repair",
            "reason": str(exc),
            "skill_doc_path": _path_str(skill_doc_path),
            "html2pptx_script_path": _path_str(skill_script_path),
        }

    parsed = _extract_json_object(raw)
    if not _is_valid_html_spec(parsed, expected_slide_count=len(slides_payload or [])):
        return None, {
            "source": "llm_repair_invalid",
            "strategy": "llm_repair",
            "reason": "invalid_repair_html_spec_json",
            "raw_preview": _preview(raw, 320),
            "skill_doc_path": _path_str(skill_doc_path),
            "html2pptx_script_path": _path_str(skill_script_path),
        }

    normalized = dict(parsed or {})
    normalized["layout"] = str(normalized.get("layout") or "LAYOUT_16x9")
    normalized, sanitize_meta = sanitize_scratch_html_spec(normalized)
    return normalized, {
        "source": "llm_repaired",
        "strategy": "llm_repair",
        "slide_count": len(normalized.get("slides") or []),
        "skill_doc_path": _path_str(skill_doc_path),
        "html2pptx_script_path": _path_str(skill_script_path),
        "sanitized_slide_count": sanitize_meta.get("slides_sanitized"),
        "sanitize_changes": sanitize_meta.get("changes"),
    }


def repair_scratch_html_spec_locally(
    *,
    current_html_spec: dict[str, Any],
    validation_error: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(current_html_spec, dict):
        return None, {"source": "local_repair_invalid", "strategy": "local_repair", "reason": "invalid_spec"}

    slides = current_html_spec.get("slides")
    if not isinstance(slides, list) or not slides:
        return None, {"source": "local_repair_invalid", "strategy": "local_repair", "reason": "missing_slides"}

    target_indices = _extract_target_slide_indices(validation_error, len(slides))
    if not target_indices:
        target_indices = list(range(len(slides)))

    error_text = str(validation_error or "").lower()
    wants_tighten = "overflow" in error_text or "too close to bottom edge" in error_text
    tighten_levels = max(1, int(settings.scratch_html_spec_local_tighten_levels))

    out = dict(current_html_spec)
    new_slides: list[Any] = []
    touched = 0
    change_rows: list[str] = []

    for idx, slide in enumerate(slides):
        if idx not in target_indices:
            new_slides.append(slide)
            continue

        if isinstance(slide, str):
            repaired_html, changes = _repair_single_slide_html_locally(
                slide,
                tighten_overflow=wants_tighten,
                tighten_levels=tighten_levels,
            )
            new_slides.append(repaired_html)
            if changes:
                touched += 1
                change_rows.append(f"slide-{idx + 1}: {', '.join(changes)}")
            continue

        if isinstance(slide, dict):
            row = dict(slide)
            html_raw = row.get("html")
            if isinstance(html_raw, str):
                repaired_html, changes = _repair_single_slide_html_locally(
                    html_raw,
                    tighten_overflow=wants_tighten,
                    tighten_levels=tighten_levels,
                )
                row["html"] = repaired_html
                if changes:
                    touched += 1
                    change_rows.append(f"slide-{idx + 1}: {', '.join(changes)}")
            new_slides.append(row)
            continue

        new_slides.append(slide)

    if touched <= 0:
        return None, {"source": "local_repair_none", "strategy": "local_repair", "reason": "no_changes"}

    out["slides"] = new_slides
    out, sanitize_meta = sanitize_scratch_html_spec(out)
    return out, {
        "source": "local_repair",
        "strategy": "local_repair",
        "slide_count": len(out.get("slides") or []),
        "sanitized_slide_count": sanitize_meta.get("slides_sanitized"),
        "sanitize_changes": (change_rows + list(sanitize_meta.get("changes") or []))[:14],
    }


def sanitize_scratch_html_spec(spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(spec, dict):
        return spec, {"slides_sanitized": 0, "changes": []}

    slides = spec.get("slides")
    if not isinstance(slides, list):
        return spec, {"slides_sanitized": 0, "changes": []}

    out = dict(spec)
    new_slides: list[Any] = []
    changes: list[str] = []
    sanitized_count = 0

    for idx, slide in enumerate(slides):
        if isinstance(slide, str):
            html_text, slide_changes = _sanitize_single_slide_html(slide)
            new_slides.append(html_text)
            if slide_changes:
                sanitized_count += 1
                changes.append(f"slide-{idx + 1}: {', '.join(slide_changes)}")
            continue

        if isinstance(slide, dict):
            row = dict(slide)
            html_raw = row.get("html")
            if isinstance(html_raw, str):
                html_text, slide_changes = _sanitize_single_slide_html(html_raw)
                row["html"] = html_text
                if slide_changes:
                    sanitized_count += 1
                    changes.append(f"slide-{idx + 1}: {', '.join(slide_changes)}")
            new_slides.append(row)
            continue

        new_slides.append(slide)

    out["slides"] = new_slides
    return out, {"slides_sanitized": sanitized_count, "changes": changes[:12]}


def _extract_target_slide_indices(validation_error: str, slide_count: int) -> list[int]:
    found: list[int] = []
    for match in _TARGET_SLIDE_RE.finditer(str(validation_error or "")):
        try:
            idx = int(match.group(1)) - 1
        except Exception:
            continue
        if 0 <= idx < slide_count and idx not in found:
            found.append(idx)
    return found


def _sanitize_single_slide_html(html_text: str) -> tuple[str, list[str]]:
    text = str(html_text or "").strip()
    if not text:
        return html_text, []

    try:
        doc = lxml_html.document_fromstring(text)
    except Exception:
        return html_text, []

    changes: list[str] = []
    changed = False

    css_changed, _ = _sanitize_style_blocks(doc, tighten_overflow=False, tighten_level=1)
    if css_changed:
        changed = True
        changes.append("style_block_normalized")

    for elem in doc.iter():
        tag = str(elem.tag or "").lower()
        if not tag:
            continue

        style_value = str(elem.attrib.get("style") or "")
        new_style, style_changed = _sanitize_style_for_tag(tag, style_value)
        if style_changed:
            changed = True
            elem.attrib["style"] = new_style
            if "style_normalized" not in changes:
                changes.append("style_normalized")

        if tag in _IGNORE_WRAP_TAGS:
            continue

        if tag not in _TEXT_TAGS and tag not in _IGNORE_WRAP_TAGS:
            if _normalize_nontext_children_to_paragraphs(elem):
                changed = True
                if "normalized_nontext_children" not in changes:
                    changes.append("normalized_nontext_children")
            if _wrap_direct_text(elem):
                changed = True
                if "wrapped_container_text" not in changes:
                    changes.append("wrapped_container_text")

    if not changed:
        return html_text, []

    try:
        rendered = lxml_html.tostring(doc, encoding="unicode", method="html")
        if "<!doctype" not in rendered.lower():
            rendered = "<!doctype html>\n" + rendered
        return rendered, changes
    except Exception:
        return html_text, []


def _repair_single_slide_html_locally(
    html_text: str,
    *,
    tighten_overflow: bool,
    tighten_levels: int,
) -> tuple[str, list[str]]:
    text = str(html_text or "").strip()
    if not text:
        return html_text, []

    try:
        doc = lxml_html.document_fromstring(text)
    except Exception:
        return html_text, []

    changed = False
    changes: list[str] = []

    css_changed, _ = _sanitize_style_blocks(doc, tighten_overflow=tighten_overflow, tighten_level=1)
    if css_changed:
        changed = True
        changes.append("style_block_normalized")

    for elem in doc.iter():
        tag = str(elem.tag or "").lower()
        if not tag:
            continue
        style_value = str(elem.attrib.get("style") or "")
        new_style, style_changed = _sanitize_style_for_tag(tag, style_value)
        if style_changed:
            changed = True
            elem.attrib["style"] = new_style
            if "style_normalized" not in changes:
                changes.append("style_normalized")
        if tag not in _TEXT_TAGS and tag not in _IGNORE_WRAP_TAGS:
            if _normalize_nontext_children_to_paragraphs(elem):
                changed = True
                if "normalized_nontext_children" not in changes:
                    changes.append("normalized_nontext_children")
            if _wrap_direct_text(elem):
                changed = True
                if "wrapped_container_text" not in changes:
                    changes.append("wrapped_container_text")

    if tighten_overflow:
        for level in range(1, max(1, int(tighten_levels)) + 1):
            tightened_in_level = False
            css_changed_in_level, _ = _sanitize_style_blocks(doc, tighten_overflow=True, tighten_level=level)
            if css_changed_in_level:
                tightened_in_level = True
                changed = True
            for elem in doc.iter():
                tag = str(elem.tag or "").lower()
                if not tag:
                    continue
                style_value = str(elem.attrib.get("style") or "")
                new_style, tightened = _tighten_style_for_overflow(tag, style_value, level=level)
                if tightened:
                    tightened_in_level = True
                    changed = True
                    elem.attrib["style"] = new_style
            if tightened_in_level and "overflow_compacted" not in changes:
                changes.append("overflow_compacted")

    if not changed:
        return html_text, []

    try:
        rendered = lxml_html.tostring(doc, encoding="unicode", method="html")
        if "<!doctype" not in rendered.lower():
            rendered = "<!doctype html>\n" + rendered
        return rendered, changes
    except Exception:
        return html_text, []


def _normalize_nontext_children_to_paragraphs(elem) -> bool:
    changed = False
    children = list(elem)
    for child in children:
        tag = str(child.tag or "").lower()
        if not tag or tag in _IGNORE_WRAP_TAGS or tag in _TEXT_TAGS:
            continue

        if _normalize_nontext_children_to_paragraphs(child):
            changed = True

        text_content = " ".join(piece.strip() for piece in child.itertext() if str(piece).strip()).strip()
        if not text_content:
            continue

        has_text_descendant = any(
            str(desc.tag or "").lower() in _TEXT_TAGS for desc in child.iterdescendants()
        )
        if has_text_descendant:
            continue

        if tag in _INLINE_TEXT_TAGS or tag == "div":
            tail_text = str(child.tail or "").strip()
            combined_text = text_content if not tail_text else f"{text_content} {tail_text}".strip()
            p = lxml_html.Element("p")
            p.text = combined_text
            style = str(child.attrib.get("style") or "").strip()
            if style:
                p.attrib["style"] = style
            pos = elem.index(child)
            child.tail = None
            elem.remove(child)
            elem.insert(pos, p)
            changed = True
    return changed


def _wrap_direct_text(elem) -> bool:
    changed = False
    lead = str(elem.text or "").strip()
    if lead:
        wrapper_tag = "li" if str(elem.tag or "").lower() in {"ul", "ol"} else "p"
        node = lxml_html.Element(wrapper_tag)
        if wrapper_tag == "li":
            p = lxml_html.Element("p")
            p.text = lead
            node.append(p)
        else:
            node.text = lead
        elem.insert(0, node)
        elem.text = None
        changed = True

    children = list(elem)
    for child in children:
        tail = str(child.tail or "").strip()
        if not tail:
            continue
        wrapper_tag = "li" if str(elem.tag or "").lower() in {"ul", "ol"} else "p"
        node = lxml_html.Element(wrapper_tag)
        if wrapper_tag == "li":
            p = lxml_html.Element("p")
            p.text = tail
            node.append(p)
        else:
            node.text = tail
        pos = elem.index(child) + 1
        elem.insert(pos, node)
        child.tail = None
        changed = True
    return changed


def _sanitize_style_for_tag(tag: str, style_value: str) -> tuple[str, bool]:
    if not style_value:
        return style_value, False

    parts = [row.strip() for row in style_value.split(";") if row.strip()]
    kept: list[str] = []
    changed = False

    for part in parts:
        if ":" not in part:
            changed = True
            continue
        key, value = part.split(":", 1)
        prop = key.strip().lower()
        raw_val = value.strip()
        val_lower = raw_val.lower()

        # html2pptx validator rejects background images.
        if prop.startswith("background-image") or ("url(" in val_lower and prop.startswith("background")):
            changed = True
            continue

        # html2pptx only supports visual box styling on DIV-like elements.
        if tag in _TEXT_TAGS and (
            prop.startswith("border") or prop.startswith("box-shadow") or prop.startswith("background")
        ):
            changed = True
            continue

        kept.append(f"{key.strip()}:{raw_val}")

    normalized = "; ".join(kept)
    return normalized, changed or (normalized != style_value.strip())


def _sanitize_style_blocks(doc, *, tighten_overflow: bool, tighten_level: int) -> tuple[bool, list[str]]:
    changed = False
    touched: list[str] = []
    for style_el in doc.xpath("//style"):
        raw_css = str(style_el.text or "")
        if not raw_css.strip():
            continue
        new_css, css_changed = _sanitize_css_text(
            raw_css,
            tighten_overflow=tighten_overflow,
            tighten_level=tighten_level,
        )
        if css_changed:
            style_el.text = new_css
            changed = True
            touched.append("style")
    return changed, touched


def _sanitize_css_text(css_text: str, *, tighten_overflow: bool, tighten_level: int) -> tuple[str, bool]:
    changed = False
    chunks: list[str] = []
    last_end = 0

    for match in _CSS_RULE_RE.finditer(css_text):
        chunks.append(css_text[last_end : match.start()])
        selectors_raw = str(match.group(1) or "")
        body_raw = str(match.group(2) or "")
        selector_is_text = _selector_targets_text(selectors_raw)
        decls_new, decls_changed = _sanitize_css_declarations(
            body_raw,
            selector_is_text=selector_is_text,
            tighten_overflow=tighten_overflow,
            tighten_level=tighten_level,
        )
        if decls_changed:
            changed = True
        chunks.append(f"{selectors_raw}{{{decls_new}}}")
        last_end = match.end()

    chunks.append(css_text[last_end:])
    out = "".join(chunks)
    return out, changed


def _sanitize_css_declarations(
    declarations: str,
    *,
    selector_is_text: bool,
    tighten_overflow: bool,
    tighten_level: int,
) -> tuple[str, bool]:
    changed = False
    compact_factor = 0.92 if tighten_level <= 1 else 0.84
    spacing_factor = 0.86 if tighten_level <= 1 else 0.72
    kept: list[str] = []

    for part in declarations.split(";"):
        row = part.strip()
        if not row:
            continue
        if ":" not in row:
            changed = True
            continue
        key, value = row.split(":", 1)
        prop = key.strip().lower()
        raw_val = value.strip()
        val_lower = raw_val.lower()

        if prop.startswith("background-image") or ("url(" in val_lower and prop.startswith("background")):
            changed = True
            continue
        if selector_is_text and (
            prop.startswith("border") or prop.startswith("box-shadow") or prop.startswith("background")
        ):
            changed = True
            continue

        new_val = raw_val
        if tighten_overflow and prop in _STYLE_NUMERIC_PROPS and "pt" in val_lower:
            if prop in {"font-size", "line-height", "letter-spacing"}:
                new_val, adjusted = _scale_pt_values(raw_val, compact_factor, min_pt=8.0)
            elif prop in {
                "margin",
                "margin-top",
                "margin-right",
                "margin-bottom",
                "margin-left",
                "padding",
                "padding-top",
                "padding-right",
                "padding-bottom",
                "padding-left",
                "gap",
                "row-gap",
                "column-gap",
            }:
                new_val, adjusted = _scale_pt_values(raw_val, spacing_factor, min_pt=0.0)
            elif prop in {"height", "max-height", "min-height"}:
                new_val, adjusted = _scale_pt_values(raw_val, compact_factor, min_pt=24.0)
            else:
                adjusted = False
            if adjusted:
                changed = True

        kept.append(f"{key.strip()}:{new_val}")

    return "; ".join(kept), changed


def _selector_targets_text(selector: str) -> bool:
    raw = str(selector or "")
    return bool(_TEXT_SELECTOR_RE.search(raw))


def _tighten_style_for_overflow(tag: str, style_value: str, *, level: int) -> tuple[str, bool]:
    if not style_value:
        return style_value, False

    compact_factor = 0.92 if level <= 1 else 0.84
    spacing_factor = 0.86 if level <= 1 else 0.72
    changed = False
    parts = [row.strip() for row in style_value.split(";") if row.strip()]
    kept: list[str] = []

    for part in parts:
        if ":" not in part:
            changed = True
            continue
        key, value = part.split(":", 1)
        prop = key.strip().lower()
        raw_val = value.strip()
        new_val = raw_val

        if prop in _STYLE_NUMERIC_PROPS and "pt" in raw_val.lower():
            if prop in {"font-size", "line-height", "letter-spacing"}:
                new_val, adjusted = _scale_pt_values(raw_val, compact_factor, min_pt=8.0)
            elif prop in {
                "margin",
                "margin-top",
                "margin-right",
                "margin-bottom",
                "margin-left",
                "padding",
                "padding-top",
                "padding-right",
                "padding-bottom",
                "padding-left",
                "gap",
                "row-gap",
                "column-gap",
            }:
                new_val, adjusted = _scale_pt_values(raw_val, spacing_factor, min_pt=0.0)
            elif prop in {"height", "max-height", "min-height"} and tag not in {"body", "html"}:
                new_val, adjusted = _scale_pt_values(raw_val, compact_factor, min_pt=36.0)
            else:
                adjusted = False
            if adjusted:
                changed = True

        kept.append(f"{key.strip()}:{new_val}")

    normalized = "; ".join(kept)
    return normalized, changed or (normalized != style_value.strip())


def _scale_pt_values(raw_value: str, factor: float, *, min_pt: float | None = None) -> tuple[str, bool]:
    changed = False

    def _repl(match: re.Match[str]) -> str:
        nonlocal changed
        try:
            original = float(match.group(1))
        except Exception:
            return match.group(0)
        scaled = original * factor
        if min_pt is not None:
            scaled = max(min_pt, scaled)
        if abs(scaled - original) < 0.15:
            return match.group(0)
        changed = True
        return f"{scaled:.2f}pt"

    new_val = _PT_VALUE_RE.sub(_repl, raw_value)
    return new_val, changed


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    raw = str(raw_text or "").strip()
    if not raw:
        return None

    candidates: list[str] = [raw]
    cleaned = _CODE_FENCE_RE.sub("", raw).strip()
    if cleaned and cleaned not in candidates:
        candidates.append(cleaned)

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first >= 0 and last > first:
        span = cleaned[first : last + 1].strip()
        if span and span not in candidates:
            candidates.append(span)

    for candidate in candidates:
        for attempt in (candidate, _repair_json_candidate(candidate)):
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return None


def _repair_json_candidate(text: str) -> str:
    repaired = _escape_newlines_in_json_strings(text)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def _escape_newlines_in_json_strings(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == '"':
            out.append(ch)
            in_string = not in_string
            continue
        if in_string and ch in ("\r", "\n"):
            if not out or out[-1] != "\\n":
                out.append("\\n")
            continue
        out.append(ch)
    return "".join(out)


def _is_valid_html_spec(spec: dict[str, Any] | None, *, expected_slide_count: int) -> bool:
    if not isinstance(spec, dict):
        return False
    slides = spec.get("slides")
    if not isinstance(slides, list) or not slides:
        return False
    if expected_slide_count > 0 and len(slides) != expected_slide_count:
        return False
    for row in slides:
        if isinstance(row, str):
            text = row.strip().lower()
            if not text or "<body" not in text:
                return False
            continue
        if isinstance(row, dict):
            html_text = str(row.get("html") or "").strip().lower()
            path_text = str(row.get("path") or "").strip()
            if html_text and "<body" in html_text:
                continue
            if path_text:
                continue
        return False
    return True


def _skill_doc_excerpt(path) -> str:
    if not path:
        return (
            "Use html2pptx-compatible HTML with 720pt x 405pt body, text tags only, "
            "list tags for bullets, and web-safe fonts."
        )
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return (
            "Use html2pptx-compatible HTML with 720pt x 405pt body, text tags only, "
            "list tags for bullets, and web-safe fonts."
        )
    trimmed = text.strip()
    return trimmed[:14000] if len(trimmed) > 14000 else trimmed


def _path_str(path) -> str | None:
    return str(path) if path else None


def _preview(text: str, limit: int = 200) -> str:
    raw = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(raw) <= limit:
        return raw
    return raw[:limit].rstrip() + " ..."


def build_scratch_html_spec(
    *,
    slides_payload: list[dict[str, Any]],
    title: str,
    theme: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    palette = _normalize_theme(theme)
    total = max(1, len(slides_payload or []))
    slides: list[str] = []
    for idx, row in enumerate(slides_payload or []):
        slides.append(
            _build_slide_html(
                slide=row or {},
                slide_index=idx,
                total_slides=total,
                deck_title=title,
                palette=palette,
            )
        )
    return {"layout": "LAYOUT_16x9", "slides": slides}


def _build_slide_html(
    *,
    slide: dict[str, Any],
    slide_index: int,
    total_slides: int,
    deck_title: str,
    palette: dict[str, str],
) -> str:
    archetype = str(slide.get("archetype") or "general").strip().lower()
    slots = _normalize_slots(slide.get("slots"))

    title = slots.get("TITLE") or slots.get("title") or deck_title or f"Slide {slide_index + 1}"
    subtitle = slots.get("SUBTITLE", "")
    citation = slots.get("CITATION", "")
    bullets = _extract_items(slots.get("BULLET_1", ""), slots.get("BULLET_2", ""), slots.get("BULLET", ""))
    body_chunks = _extract_items(slots.get("BODY_1", ""), slots.get("BODY", ""))

    if archetype in {"section_break", "quote", "closing"}:
        return _build_hero_slide(
            title=title,
            subtitle=subtitle or (body_chunks[0] if body_chunks else ""),
            citation=citation,
            slide_index=slide_index,
            total_slides=total_slides,
            palette=palette,
        )

    if archetype == "comparison":
        return _build_comparison_slide(
            title=title,
            left_items=bullets,
            right_items=body_chunks,
            citation=citation,
            slide_index=slide_index,
            total_slides=total_slides,
            palette=palette,
        )

    if archetype == "timeline":
        timeline_points = bullets or body_chunks
        return _build_timeline_slide(
            title=title,
            points=timeline_points,
            citation=citation,
            slide_index=slide_index,
            total_slides=total_slides,
            palette=palette,
        )

    return _build_standard_slide(
        title=title,
        subtitle=subtitle,
        bullets=bullets,
        body=body_chunks,
        citation=citation,
        slide_index=slide_index,
        total_slides=total_slides,
        palette=palette,
    )


def _build_hero_slide(
    *,
    title: str,
    subtitle: str,
    citation: str,
    slide_index: int,
    total_slides: int,
    palette: dict[str, str],
) -> str:
    subtitle_block = ""
    if subtitle:
        subtitle_block = (
            f'<p style="margin:14pt 0 0 0;font-size:17pt;line-height:1.35;color:{palette["textLight"]};">'
            f"{_esc(subtitle)}</p>"
        )
    citation_block = _citation_html(citation, palette["textLight"])
    body = f"""
<div style="width:100%;height:333pt;box-sizing:border-box;border:2pt solid {palette['accent']};border-radius:14pt;padding:34pt;background:transparent;">
  <p style="margin:0 0 12pt 0;font-size:12pt;letter-spacing:1.2pt;color:{palette['accent']};">SLIDE {slide_index + 1} / {total_slides}</p>
  <h1 style="margin:0;font-size:44pt;line-height:1.06;color:{palette['textLight']};font-family:{_esc(palette['headerFont'])};">{_esc(title)}</h1>
  {subtitle_block}
  {citation_block}
</div>
"""
    return _document_html(body=body, palette=palette, dark=True)


def _build_comparison_slide(
    *,
    title: str,
    left_items: list[str],
    right_items: list[str],
    citation: str,
    slide_index: int,
    total_slides: int,
    palette: dict[str, str],
) -> str:
    left = _list_html(left_items or ["No left-side points provided."], palette["text"])
    right = _list_html(right_items or ["No right-side points provided."], palette["text"])
    body = f"""
{_header_html(title, slide_index, total_slides, palette)}
<div style="display:flex;gap:14pt;">
  <div style="flex:1;min-width:0;height:250pt;box-sizing:border-box;background:{palette['cardFill']};border:1pt solid {palette['cardBorder']};border-radius:10pt;padding:14pt;">
    <h2 style="margin:0 0 8pt 0;font-size:17pt;color:{palette['primary']};font-family:{_esc(palette['headerFont'])};">Perspective A</h2>
    {left}
  </div>
  <div style="flex:1;min-width:0;height:250pt;box-sizing:border-box;background:{palette['cardFill']};border:1pt solid {palette['cardBorder']};border-radius:10pt;padding:14pt;">
    <h2 style="margin:0 0 8pt 0;font-size:17pt;color:{palette['secondary']};font-family:{_esc(palette['headerFont'])};">Perspective B</h2>
    {right}
  </div>
</div>
{_citation_html(citation, palette["muted"])}
"""
    return _document_html(body=body, palette=palette, dark=False)


def _build_timeline_slide(
    *,
    title: str,
    points: list[str],
    citation: str,
    slide_index: int,
    total_slides: int,
    palette: dict[str, str],
) -> str:
    if not points:
        points = ["No timeline points were provided."]
    rows = []
    for point in points[:6]:
        rows.append(
            f"""
<div style="display:flex;align-items:flex-start;margin-bottom:8pt;">
  <div style="width:18pt;height:18pt;border-radius:50%;background:{palette['accent']};margin:3pt 10pt 0 0;"></div>
  <p style="margin:0;font-size:14pt;line-height:1.35;color:{palette['text']};">{_esc(point)}</p>
</div>
"""
        )
    body = f"""
{_header_html(title, slide_index, total_slides, palette)}
<div style="width:100%;height:258pt;box-sizing:border-box;background:{palette['cardFill']};border:1pt solid {palette['cardBorder']};border-radius:10pt;padding:16pt;">
  {''.join(rows)}
</div>
{_citation_html(citation, palette["muted"])}
"""
    return _document_html(body=body, palette=palette, dark=False)


def _build_standard_slide(
    *,
    title: str,
    subtitle: str,
    bullets: list[str],
    body: list[str],
    citation: str,
    slide_index: int,
    total_slides: int,
    palette: dict[str, str],
) -> str:
    subtitle_block = (
        f'<p style="margin:8pt 0 0 0;font-size:14pt;line-height:1.3;color:{palette["muted"]};">{_esc(subtitle)}</p>'
        if subtitle
        else ""
    )
    bullet_html = _list_html(bullets or ["No key points provided."], palette["text"])
    body_html = _list_html(body or ["No supporting detail provided."], palette["text"])
    content = f"""
{_header_html(title, slide_index, total_slides, palette)}
{subtitle_block}
<div style="display:flex;gap:14pt;margin-top:12pt;">
  <div style="flex:1;min-width:0;height:232pt;box-sizing:border-box;background:{palette['cardFill']};border:1pt solid {palette['cardBorder']};border-radius:10pt;padding:14pt;">
    <h2 style="margin:0 0 8pt 0;font-size:16pt;color:{palette['primary']};font-family:{_esc(palette['headerFont'])};">Highlights</h2>
    {bullet_html}
  </div>
  <div style="flex:1;min-width:0;height:232pt;box-sizing:border-box;background:{palette['cardFill']};border:1pt solid {palette['cardBorder']};border-radius:10pt;padding:14pt;">
    <h2 style="margin:0 0 8pt 0;font-size:16pt;color:{palette['secondary']};font-family:{_esc(palette['headerFont'])};">Details</h2>
    {body_html}
  </div>
</div>
{_citation_html(citation, palette["muted"])}
"""
    return _document_html(body=content, palette=palette, dark=False)


def _header_html(title: str, slide_index: int, total_slides: int, palette: dict[str, str]) -> str:
    return (
        f'<p style="margin:0 0 6pt 0;font-size:11pt;letter-spacing:1pt;color:{palette["muted"]};">'
        f"SLIDE {slide_index + 1} / {total_slides}</p>"
        f'<h1 style="margin:0;font-size:34pt;line-height:1.1;color:{palette["text"]};font-family:{_esc(palette["headerFont"])};">'
        f"{_esc(title)}</h1>"
    )


def _citation_html(citation: str, color: str) -> str:
    if not citation:
        return ""
    return (
        f'<p style="margin:10pt 0 0 0;font-size:10.5pt;line-height:1.25;color:{color};font-style:italic;">'
        f"{_esc(citation)}</p>"
    )


def _list_html(items: list[str], color: str) -> str:
    li_blocks = []
    for item in items[:6]:
        li_blocks.append(
            f'<li style="margin:0 0 6pt 0;"><p style="margin:0;font-size:13.5pt;line-height:1.32;color:{color};">{_esc(item)}</p></li>'
        )
    return f'<ul style="margin:0;padding-left:18pt;">{"".join(li_blocks)}</ul>'


def _document_html(*, body: str, palette: dict[str, str], dark: bool) -> str:
    bg = palette["darkBackground"] if dark else palette["background"]
    text = palette["textLight"] if dark else palette["text"]
    return f"""<!doctype html>
<html>
<body style="margin:0;width:720pt;height:405pt;display:flex;flex-direction:column;justify-content:flex-start;background:{bg};color:{text};font-family:{_esc(palette['bodyFont'])};overflow:hidden;">
<div style="width:720pt;height:405pt;box-sizing:border-box;padding:24pt;display:flex;flex-direction:column;">
{body}
</div>
</body>
</html>"""


def _clean_slot_text(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = _CODE_FENCE_RE.sub("", text)
    text = _TOOL_ARTIFACT_RE.sub(" ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_slots(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key in _TEXT_SLOT_KEYS:
        raw = value.get(key)
        if raw is None:
            continue
        text = _clean_slot_text(str(raw))
        if text:
            out[key] = text
    return out


def _extract_items(*chunks: str) -> list[str]:
    merged = "\n".join(_clean_slot_text(str(chunk or "")) for chunk in chunks).strip()
    if not merged:
        return []
    merged = merged.replace("\r", "\n").replace("|", "\n")
    merged = re.sub(r"[\u2022\u25CF\u25AA\u25E6]", "\n", merged)
    lines: list[str] = []
    for raw in merged.split("\n"):
        row = raw.strip()
        if not row:
            continue
        row = re.sub(r"^[-*]\s*", "", row)
        row = re.sub(r"^\d+[.)]\s*", "", row)
        row = row.strip()
        if row:
            lines.append(row)
    if len(lines) == 1 and len(lines[0]) > 140:
        lines = [part.strip() for part in _SENTENCE_SPLIT_RE.split(lines[0]) if part.strip()]
    return lines[:8]


def _normalize_theme(theme: str | dict[str, Any] | None) -> dict[str, str]:
    result = dict(_DEFAULT_THEME)
    if isinstance(theme, dict):
        for key, value in theme.items():
            if key not in result:
                continue
            if key in {"headerFont", "bodyFont"}:
                text = str(value or "").strip()
                if text:
                    result[key] = text
                continue
            text = str(value or "").strip().replace("#", "")
            if _HEX6_RE.fullmatch(text):
                result[key] = text.upper()
    for key in (
        "primary",
        "secondary",
        "accent",
        "background",
        "darkBackground",
        "text",
        "textLight",
        "muted",
        "cardFill",
        "cardBorder",
    ):
        result[key] = f"#{result[key]}"
    return result


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)
