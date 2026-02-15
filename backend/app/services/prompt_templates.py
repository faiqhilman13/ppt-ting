from __future__ import annotations

import json

from app.services.pptx_skill_loader import build_pptx_skill_context
from app.services.slide_archetypes import archetype_examples, archetype_guidance, slot_budget


def _slot_context(slide: dict) -> dict[str, dict]:
    context: dict[str, dict] = {}
    for binding in slide.get("bindings", []) or []:
        slot = str(binding.get("slot", "")).upper()
        if not slot:
            continue

        entry = context.setdefault(slot, {"sources": []})
        source = {
            "kind": binding.get("kind"),
            "shape_id": binding.get("shape_id"),
            "shape_name": binding.get("shape_name"),
            "width_inches": binding.get("width_inches"),
            "height_inches": binding.get("height_inches"),
            "font_size_pt": binding.get("font_size_pt"),
            "existing_text": binding.get("existing_text"),
        }
        if binding.get("row") is not None:
            source["row"] = binding.get("row")
        if binding.get("col") is not None:
            source["col"] = binding.get("col")
        entry["sources"].append(source)

    compact: dict[str, dict] = {}
    for slot, row in context.items():
        primary = row["sources"][0]
        compact[slot] = {
            "kind": primary.get("kind"),
            "shape_id": primary.get("shape_id"),
            "shape_name": primary.get("shape_name"),
            "width_inches": primary.get("width_inches"),
            "height_inches": primary.get("height_inches"),
            "font_size_pt": primary.get("font_size_pt"),
            "existing_text": primary.get("existing_text"),
            "binding_count": len(row["sources"]),
        }
        if "row" in primary:
            compact[slot]["row"] = primary["row"]
        if "col" in primary:
            compact[slot]["col"] = primary["col"]
    return compact


def _slide_brief(slide: dict) -> dict:
    slots = slide.get("slots", [])
    archetype = slide.get("archetype", "general")
    slot_context = _slot_context(slide)
    brief = {
        "template_slide_index": slide.get("index"),
        "archetype": archetype,
        "guidance": archetype_guidance(archetype),
        "slots": slots,
        "slot_context": slot_context,
        "slot_budgets": {slot: slot_budget(archetype, slot, slot_context.get(slot)) for slot in slots},
    }
    if slide.get("narrative_role"):
        brief["narrative_role"] = slide.get("narrative_role")
    if slide.get("key_message"):
        brief["key_message"] = slide.get("key_message")
    return brief


def _research_brief(research_chunks: list[dict], max_items: int = 8) -> list[dict]:
    brief = []
    for idx, chunk in enumerate(research_chunks[:max_items]):
        use_excerpt = idx < 4
        content = chunk.get("excerpt", "") if use_excerpt else chunk.get("snippet", "")
        clipped = (content or "")[: (800 if use_excerpt else 260)]
        brief.append(
            {
                "source_id": chunk.get("source_id"),
                "title": chunk.get("title"),
                "url": chunk.get("url"),
                "content": clipped,
                "content_type": "excerpt" if use_excerpt else "snippet",
            }
        )
    return brief


def build_generation_prompts(
    *,
    prompt: str,
    extra_instructions: str | None,
    selected_slides: list[dict],
    research_chunks: list[dict],
    template_bound: bool = True,
    deck_thesis: str | None = None,
) -> tuple[str, str]:
    skill_context = build_pptx_skill_context(mode="generate", template_bound=template_bound)
    task_lines = [
        "## Runtime Task (Generate)",
        "- Produce concise, executive-grade slot values that fit provided character budgets.",
        "- Never invent slot names.",
        "- Use citation language when citation/source slots exist.",
        "- Return STRICT JSON only with shape:",
        '{"slides":[{"template_slide_index":int,"slots":{"SLOT_NAME":"value"}}]}',
    ]

    if template_bound:
        task_lines[1:1] = [
            "- You are generating slot content for an existing PPTX template-bound workflow.",
            "- Follow the PPTX skill guidance for template-aware editing decisions.",
        ]
    else:
        task_lines[1:1] = [
            "- You are generating slot content for NEW PPTX slides created from scratch.",
            "- Follow the PPTX scratch-creation guidance and keep each slide coherent as a standalone layout.",
        ]
    if deck_thesis:
        task_lines.insert(1, f"- DECK THESIS: {deck_thesis}")
        task_lines.insert(2, "- Every slide must clearly advance this thesis.")

    system = (
        f"{skill_context}\n\n"
        + "\n".join(task_lines)
    )

    payload = {
        "task": "generate",
        "prompt": prompt,
        "deck_thesis": deck_thesis,
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

    skill_context = build_pptx_skill_context(mode="revise", template_bound=True)
    system = (
        f"{skill_context}\n\n"
        "## Runtime Task (Revise)\n"
        "- You are revising existing slot values for an existing PPTX template-bound workflow.\n"
        "- Follow the PPTX skill guidance for safe edits that preserve structure and fidelity.\n"
        "- Preserve slide intent and formatting constraints.\n"
        "- Keep slot names unchanged.\n"
        "- Respect slot budgets.\n"
        "- Return STRICT JSON only with shape:\n"
        '{"slides":[{"template_slide_index":int,"slots":{"SLOT_NAME":"value"}}]}'
    )

    payload = {
        "task": "revise",
        "revision_prompt": revision_prompt,
        "slides": revision_targets,
        "research": _research_brief(research_chunks),
        "archetype_examples": archetype_examples(),
    }
    return system, json.dumps(payload)
