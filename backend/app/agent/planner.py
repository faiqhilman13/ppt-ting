from __future__ import annotations

from typing import Any

from app.config import settings


def build_generation_plan(
    *,
    creation_mode: str,
    quality_profile: str,
    selected_slides: list[dict[str, Any]],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for slide in selected_slides:
        steps.append(
            {
                "stage": "research",
                "tool": "research.route_sources",
                "slide_index": int(slide.get("index", -1)),
            }
        )

    steps.append({"stage": "qa", "tool": "qa.content_check"})
    if quality_profile in {"balanced", "high_fidelity"}:
        steps.append({"stage": "qa", "tool": "qa.visual_check"})

    capped = steps[: max(1, settings.max_plan_steps)]
    return {
        "mode": "bounded",
        "creation_mode": creation_mode,
        "quality_profile": quality_profile,
        "steps": capped,
    }

