from pathlib import Path
from urllib.parse import quote

from app.config import settings


def build_editor_config(deck_id: str, version: int) -> dict:
    download_url = f"{settings.public_base_url}/api/decks/{quote(deck_id)}/download?version={version}"
    return {
        "document": {
            "fileType": "pptx",
            "key": f"{deck_id}-v{version}",
            "title": f"{deck_id}-v{version}.pptx",
            "url": download_url,
        },
        "documentType": "slide",
        "editorConfig": {
            "mode": "edit",
            "callbackUrl": f"{settings.public_base_url}/api/editor/callback?deck_id={quote(deck_id)}",
        },
        "height": "100%",
        "width": "100%",
    }


def save_manual_edit(source_bytes: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source_bytes)
