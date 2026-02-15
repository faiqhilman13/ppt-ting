import json
from pathlib import Path
from uuid import uuid4

from app.config import settings


def make_file_path(kind: str, extension: str, stem: str | None = None) -> Path:
    folder = settings.storage_root / kind
    folder.mkdir(parents=True, exist_ok=True)
    safe_stem = stem or str(uuid4())
    return folder / f"{safe_stem}.{extension.lstrip('.')}"


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))
