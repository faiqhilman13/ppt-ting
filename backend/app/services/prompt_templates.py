from __future__ import annotations

import json

from app.services.slide_archetypes import archetype_examples, archetype_guidance, slot_budget


def _slide_brief(slide: dict) -> dict:
    slots = slide.get("slots", [])
    archetype = slide.get("archetype", "general")
    return {
        "template_slide_index": slide.get("index"),
        "archetype": archetype,
        "guidance": archetype_guidance(archetype),
        "slots": slots,
        "slot_budgets": {slot: slot_budget(archetype, slot) for slot in slots},
    }


def _research_brief(research_chunks: list[dict], max_items: int = 8) -> list[dict]:
    brief = []
    for chunk in research_chunks[:max_items]:
        brief.append(
            {
                "source_id": chunk.get("source_id"),
                "title": chunk.get("title"),
                "url": chunk.get("url"),
                "snippet": (chunk.get("snippet") or "")[:260],
            }
        )
    return brief


def build_generation_prompts(
    *,
    prompt: str,
    extra_instructions: str | None,
    selected_slides: list[dict],
    research_chunks: list[dict],
) -> tuple[str, str]:
    system = (
        "You are an enterprise presentation writing engine. "
        "Write concise, executive-grade slot values that fit the provided character budgets. "
        "Return STRICT JSON only with shape: "
        '{"slides":[{"template_slide_index":int,"slots":{"SLOT_NAME":"value"}}]}. '
        "Never invent slot names. Use citations when citation/source slots exist."
    )

    payload = {
        "task": "generate",
        "prompt": prompt,
        "extra_instructions": extra_instructions,
        "slides": [_slide_brief(slide) for slide in selected_slides],
        "research": _research_brief(research_chunks),
        "archetype_examples": archetype_examples(),
    }
    return system, json.dumps(payload)


def build_revision_prompts(
    *,
    revision_prompt: str,
    existing_slides: list[dict],
    template_manifest: dict,
    research_chunks: list[dict],
) -> tuple[str, str]:
    by_index = {int(slide.get("index", i)): slide for i, slide in enumerate(template_manifest.get("slides", []))}

    revision_targets = []
    for row in existing_slides:
        idx = int(row.get("template_slide_index", -1))
        spec = by_index.get(idx, {"index": idx, "archetype": "general", "slots": list((row.get("slots") or {}).keys())})
        revision_targets.append(
            {
                "template_slide_index": idx,
                "current_slots": row.get("slots", {}),
                "slide_spec": _slide_brief(spec),
            }
        )

    system = (
        "You are revising presentation slot values while preserving slide intent and formatting constraints. "
        "Return STRICT JSON only with shape: "
        '{"slides":[{"template_slide_index":int,"slots":{"SLOT_NAME":"value"}}]}. '
        "Keep slot names unchanged and respect slot budgets."
    )

    payload = {
        "task": "revise",
        "revision_prompt": revision_prompt,
        "slides": revision_targets,
        "research": _research_brief(research_chunks),
        "archetype_examples": archetype_examples(),
    }
    return system, json.dumps(payload)
