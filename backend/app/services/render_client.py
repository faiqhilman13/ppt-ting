from pathlib import Path

import requests

from app.config import settings


def render_pptx(
    deck_id: str,
    version: int,
    slides: list[dict],
    output_path: Path,
    template_manifest: dict,
    template_path: Path,
    base_pptx_path: Path | None = None,
) -> None:
    payload = {
        "deckId": deck_id,
        "version": version,
        "slides": slides,
        "templateManifest": template_manifest,
        "templatePath": str(template_path),
        "basePptxPath": str(base_pptx_path) if base_pptx_path else None,
        "outputPath": str(output_path),
    }
    response = requests.post(f"{settings.renderer_url}/render", json=payload, timeout=180)
    response.raise_for_status()
