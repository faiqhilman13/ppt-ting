from __future__ import annotations

from pathlib import Path

from app.config import settings


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for row in paths:
        key = str(row.resolve()) if row.exists() else str(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def candidate_skill_roots() -> list[Path]:
    roots: list[Path] = []
    if settings.pptx_skill_root:
        roots.append(Path(settings.pptx_skill_root))

    if settings.pptx_skill_strict:
        return _dedupe_paths(roots)

    # Common local defaults for host runs.
    roots.append(Path.home() / ".codex" / "skills" / "pptx")
    roots.append(Path("C:/Users/faiqh/.codex/skills/pptx"))

    # Bundled fallback docs/scripts available in this repo.
    roots.append(Path(__file__).resolve().parent / "pptx_skill_bundle")

    return _dedupe_paths(roots)


def resolve_skill_path(relative_path: str) -> Path | None:
    normalized = str(relative_path or "").strip().replace("\\", "/")
    if not normalized:
        return None
    for root in candidate_skill_roots():
        path = root / normalized
        if path.exists():
            return path
    return None
