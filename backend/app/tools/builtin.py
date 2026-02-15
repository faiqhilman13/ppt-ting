from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from pptx import Presentation

from app.config import settings
from app.services.pptx_skill_loader import resolve_pptx_thumbnail_script
from app.services.slide_archetypes import classify_slot, slot_budget
from app.tools.base import ToolContext, ToolResult

_STOPWORDS = {
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


def _extract_keywords(*parts: str) -> set[str]:
    joined = " ".join(part or "" for part in parts).lower()
    return {token for token in re.findall(r"[a-z]{3,}", joined) if token not in _STOPWORDS}


def _slot_context_for_slide(slide_spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    for binding in slide_spec.get("bindings", []) or []:
        slot = str(binding.get("slot", "")).strip()
        if not slot or slot in context:
            continue
        context[slot] = {
            "width_inches": binding.get("width_inches"),
            "height_inches": binding.get("height_inches"),
            "font_size_pt": binding.get("font_size_pt"),
        }
    return context


class ResearchRouteSourcesTool:
    name = "research.route_sources"
    input_schema = {
        "type": "object",
        "properties": {
            "slide_spec": {"type": "object"},
            "research_chunks": {"type": "array"},
            "max_per_slide": {"type": "integer"},
        },
        "required": ["slide_spec", "research_chunks"],
        "additionalProperties": False,
    }

    def run(self, tool_input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        slide_spec = tool_input.get("slide_spec") or {}
        all_chunks = tool_input.get("research_chunks") or []
        max_per_slide = int(tool_input.get("max_per_slide") or 3)
        keywords = _extract_keywords(
            str(slide_spec.get("narrative_role", "")),
            str(slide_spec.get("key_message", "")),
            str(slide_spec.get("name", "")),
            str(slide_spec.get("archetype", "")),
        )
        if not keywords:
            selected = all_chunks[:max_per_slide]
        else:
            scored: list[tuple[int, int, dict[str, Any]]] = []
            for idx, chunk in enumerate(all_chunks):
                haystack = " ".join(
                    [
                        str(chunk.get("title", "")).lower(),
                        str(chunk.get("snippet", "")).lower(),
                        str(chunk.get("excerpt", "")).lower(),
                    ]
                )
                overlap = sum(1 for keyword in keywords if keyword in haystack)
                scored.append((overlap, -idx, chunk))
            scored.sort(reverse=True)
            selected = [row[2] for row in scored if row[0] > 0][:max_per_slide]
            if len(selected) < max_per_slide:
                seen = {str(item.get("source_id", "")) for item in selected}
                for chunk in all_chunks:
                    source_id = str(chunk.get("source_id", ""))
                    if source_id in seen:
                        continue
                    seen.add(source_id)
                    selected.append(chunk)
                    if len(selected) >= max_per_slide:
                        break

        return ToolResult(
            ok=True,
            summary=f"Routed {len(selected)} sources for slide",
            metrics={"selected_count": len(selected)},
            payload={"chunks": selected},
        )


class QAContentCheckTool:
    name = "qa.content_check"
    input_schema = {
        "type": "object",
        "properties": {
            "slides_payload": {"type": "array"},
            "template_manifest": {"type": "object"},
        },
        "required": ["slides_payload", "template_manifest"],
        "additionalProperties": False,
    }

    def run(self, tool_input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        slides_payload = tool_input.get("slides_payload") or []
        template_manifest = tool_input.get("template_manifest") or {}
        manifest_by_index = {
            int(row.get("index", i)): row for i, row in enumerate(template_manifest.get("slides", []) or [])
        }

        issues: list[dict[str, Any]] = []
        for row in slides_payload:
            idx = int(row.get("template_slide_index", -1))
            spec = manifest_by_index.get(idx, {})
            expected_slots = {str(slot) for slot in spec.get("slots", [])}
            current_slots = {str(k): str(v) for k, v in (row.get("slots") or {}).items()}

            missing = sorted(slot for slot in expected_slots if not current_slots.get(slot, "").strip())
            unresolved_tokens: list[str] = []
            for slot_name, value in current_slots.items():
                if "{{" in value and "}}" in value:
                    unresolved_tokens.append(slot_name)
            missing_citation = []
            for slot_name, value in current_slots.items():
                if classify_slot(slot_name) == "CITATION" and value.strip():
                    if not value.lower().startswith("source:"):
                        missing_citation.append(slot_name)

            if missing or unresolved_tokens or missing_citation:
                severity = "critical" if missing else "warning"
                issues.append(
                    {
                        "slide_index": idx,
                        "severity": severity,
                        "missing_slots": missing,
                        "unresolved_tokens": unresolved_tokens,
                        "citation_format": missing_citation,
                    }
                )

        critical_count = sum(1 for row in issues if row.get("severity") == "critical")
        warnings: list[str] = []
        if critical_count:
            warnings.append(f"{critical_count} critical issues")
        return ToolResult(
            ok=True,
            summary=f"Content check found {len(issues)} issues",
            metrics={"issue_count": len(issues), "critical_count": critical_count},
            payload={"issues": issues},
            warnings=warnings,
        )


class QAVisualCheckTool:
    name = "qa.visual_check"
    input_schema = {
        "type": "object",
        "properties": {
            "slides_payload": {"type": "array"},
            "template_manifest": {"type": "object"},
        },
        "required": ["slides_payload", "template_manifest"],
        "additionalProperties": False,
    }

    def run(self, tool_input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        slides_payload = tool_input.get("slides_payload") or []
        template_manifest = tool_input.get("template_manifest") or {}
        manifest_by_index = {
            int(row.get("index", i)): row for i, row in enumerate(template_manifest.get("slides", []) or [])
        }

        issues: list[dict[str, Any]] = []
        for row in slides_payload:
            idx = int(row.get("template_slide_index", -1))
            spec = manifest_by_index.get(idx, {})
            archetype = str(spec.get("archetype") or "general")
            slot_context = _slot_context_for_slide(spec)
            for slot_name, value in (row.get("slots") or {}).items():
                text = str(value or "")
                budget = slot_budget(archetype, str(slot_name), slot_context.get(str(slot_name)))
                if budget <= 0:
                    continue
                ratio = len(text) / max(1, budget)
                if ratio > 1.05:
                    issues.append(
                        {
                            "slide_index": idx,
                            "slot": str(slot_name),
                            "severity": "critical" if ratio > 1.25 else "warning",
                            "issue_type": "overflow_risk",
                            "char_count": len(text),
                            "budget": budget,
                            "ratio": round(ratio, 2),
                        }
                    )

        critical_count = sum(1 for row in issues if row.get("severity") == "critical")
        warning_count = sum(1 for row in issues if row.get("severity") != "critical")
        return ToolResult(
            ok=True,
            summary=f"Visual QA found {len(issues)} potential layout issues",
            metrics={
                "issue_count": len(issues),
                "critical_count": critical_count,
                "warning_count": warning_count,
            },
            payload={"issues": issues},
        )


class RenderThumbnailGridTool:
    name = "render.thumbnail_grid"
    input_schema = {
        "type": "object",
        "properties": {
            "pptx_path": {"type": "string"},
            "output_prefix": {"type": "string"},
            "cols": {"type": "integer"},
        },
        "required": ["pptx_path"],
        "additionalProperties": False,
    }

    def run(self, tool_input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        pptx_path = Path(str(tool_input.get("pptx_path") or "")).expanduser()
        if not pptx_path.exists():
            return ToolResult(ok=False, summary="PPTX does not exist", error=f"Missing file: {pptx_path}")

        slide_count = len(Presentation(str(pptx_path)).slides)
        script_path = resolve_pptx_thumbnail_script()
        if script_path is None:
            return ToolResult(
                ok=False,
                summary="PPTX skill thumbnail script not found",
                error="Could not locate scripts/thumbnail.py in PPTX skill roots",
                metrics={"slide_count": slide_count},
                artifacts={"pptx_path": str(pptx_path)},
            )

        requested_prefix = str(tool_input.get("output_prefix") or "").strip()
        cols = int(tool_input.get("cols") or 3)
        thumbs_root = settings.storage_root / "thumbnails"
        thumbs_root.mkdir(parents=True, exist_ok=True)
        if requested_prefix:
            output_prefix = Path(requested_prefix)
            if not output_prefix.is_absolute():
                output_prefix = thumbs_root / output_prefix
        else:
            suffix = str(ctx.job_id or "adhoc")
            output_prefix = thumbs_root / f"{pptx_path.stem}-{suffix}"

        output_prefix.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(script_path),
            str(pptx_path),
            str(output_prefix),
            "--cols",
            str(cols),
        ]
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(script_path.parent),
            timeout=max(10, int(ctx.timeout_seconds)),
        )

        generated = sorted(output_prefix.parent.glob(f"{output_prefix.name}*.jpg"))
        artifacts: dict[str, str] = {"pptx_path": str(pptx_path)}
        for idx, image_path in enumerate(generated[:12], start=1):
            artifacts[f"thumbnail_{idx}"] = str(image_path)

        stderr_preview = (proc.stderr or "").strip()
        stdout_preview = (proc.stdout or "").strip()
        if proc.returncode != 0:
            return ToolResult(
                ok=False,
                summary="PPTX thumbnail generation failed",
                error=(stderr_preview or stdout_preview or f"thumbnail.py exited with {proc.returncode}")[:1200],
                metrics={"slide_count": slide_count, "thumbnail_count": len(generated)},
                artifacts=artifacts,
                warnings=[
                    "Ensure LibreOffice (soffice), poppler-utils (pdftoppm), Pillow, and defusedxml are installed."
                ],
            )

        return ToolResult(
            ok=True,
            summary=f"Generated {len(generated)} thumbnail grid image(s) via PPTX skill thumbnail.py",
            metrics={"slide_count": slide_count, "thumbnail_count": len(generated), "cols": cols},
            artifacts=artifacts,
            payload={
                "script_path": str(script_path),
                "stdout": stdout_preview[:1200],
            },
        )
