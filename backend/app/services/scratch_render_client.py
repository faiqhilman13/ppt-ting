from __future__ import annotations

import logging
from pathlib import Path

import requests

from app.config import settings
from app.services.scratch_pptx_service import build_scratch_pptx

logger = logging.getLogger(__name__)

_THEME_MAP = {
    "default": "midnight_executive",
    "corporate": "teal_trust",
    "dark": "midnight_executive",
}


def render_scratch_pptx(
    *,
    slides_payload: list[dict],
    output_path: Path,
    title: str,
    theme: str | dict = "default",
) -> None:
    """Render a scratch deck via the PptxGenJS scratch-renderer service.

    Falls back to the built-in python-pptx builder when the service is unavailable.

    Args:
        theme: Either a preset name string (mapped via _THEME_MAP) or a full
               theme dict with all 12 properties (passed through directly).
    """
    if isinstance(theme, dict):
        resolved_theme = theme
    else:
        resolved_theme = _THEME_MAP.get(theme, theme)

    payload = {
        "slides": slides_payload,
        "title": title,
        "theme": resolved_theme,
        "outputPath": str(output_path),
    }

    try:
        resp = requests.post(
            f"{settings.scratch_renderer_url}/render",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        logger.info("scratch-renderer produced %s", output_path)
    except Exception:
        logger.warning(
            "scratch-renderer unavailable, falling back to python-pptx builder",
            exc_info=True,
        )
        fallback_theme = theme if isinstance(theme, str) else "default"
        build_scratch_pptx(
            slides_payload=slides_payload,
            output_path=output_path,
            title=title,
            theme=fallback_theme,
        )
