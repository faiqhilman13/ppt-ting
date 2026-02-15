import re
from collections import defaultdict
from pathlib import Path

from pptx import Presentation

from app.services.slide_archetypes import infer_archetype

TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_:-]+)\s*\}\}")


def _extract_tokens(text: str) -> list[str]:
    if not text:
        return []
    return sorted({match.group(1).upper() for match in TOKEN_PATTERN.finditer(text)})


def _auto_slot_name(shape, counters: dict[str, int]) -> str | None:
    if not getattr(shape, "is_placeholder", False):
        return None

    try:
        ph_type = str(shape.placeholder_format.type).upper()
    except Exception:
        ph_type = shape.name.upper()

    if "TITLE" in ph_type and "SUBTITLE" not in ph_type:
        counters["TITLE"] += 1
        return "TITLE" if counters["TITLE"] == 1 else f"TITLE_{counters['TITLE']}"
    if "SUBTITLE" in ph_type:
        counters["SUBTITLE"] += 1
        return "SUBTITLE" if counters["SUBTITLE"] == 1 else f"SUBTITLE_{counters['SUBTITLE']}"

    counters["BODY"] += 1
    return f"BODY_{counters['BODY']}"


def parse_template_manifest(template_path: Path) -> dict:
    presentation = Presentation(str(template_path))

    slides: list[dict] = []
    all_slots: set[str] = set()

    for slide_index, slide in enumerate(presentation.slides):
        slot_counters: dict[str, int] = defaultdict(int)
        bindings: list[dict] = []

        for shape in slide.shapes:
            shape_id = int(getattr(shape, "shape_id", -1))
            shape_name = str(getattr(shape, "name", f"shape-{shape_id}"))

            if getattr(shape, "has_text_frame", False):
                text = shape.text_frame.text or ""

                tokens = _extract_tokens(text)
                for token in tokens:
                    bindings.append(
                        {
                            "slot": token,
                            "kind": "token_text",
                            "shape_id": shape_id,
                            "shape_name": shape_name,
                        }
                    )
                    all_slots.add(token)

                # Auto-bind placeholders when explicit tokens are absent.
                if not tokens:
                    auto_slot = _auto_slot_name(shape, slot_counters)
                    if auto_slot:
                        bindings.append(
                            {
                                "slot": auto_slot,
                                "kind": "shape_text",
                                "shape_id": shape_id,
                                "shape_name": shape_name,
                            }
                        )
                        all_slots.add(auto_slot)

            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        tokens = _extract_tokens(cell.text or "")
                        for token in tokens:
                            bindings.append(
                                {
                                    "slot": token,
                                    "kind": "token_table",
                                    "shape_id": shape_id,
                                    "shape_name": shape_name,
                                }
                            )
                            all_slots.add(token)

        # De-duplicate exact bindings.
        unique_bindings = []
        seen = set()
        for binding in bindings:
            key = (binding["slot"], binding["kind"], binding["shape_id"])
            if key in seen:
                continue
            seen.add(key)
            unique_bindings.append(binding)

        slide_slots = sorted({binding["slot"] for binding in unique_bindings})
        archetype = infer_archetype(slide_slots)

        slides.append(
            {
                "index": slide_index,
                "name": slide.slide_layout.name if slide.slide_layout else f"slide-{slide_index}",
                "slots": slide_slots,
                "archetype": archetype,
                "bindings": unique_bindings,
            }
        )

    return {
        "version": "template_fidelity_v1",
        "slide_count": len(slides),
        "slides": slides,
        "slot_types": sorted(all_slots),
    }
