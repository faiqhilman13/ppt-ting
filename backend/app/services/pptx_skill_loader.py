from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import settings


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    if settings.pptx_skill_root:
        roots.append(Path(settings.pptx_skill_root))

    roots.append(Path.home() / ".codex" / "skills" / "pptx")
    roots.append(Path(__file__).with_name("pptx_skill_bundle"))
    return roots


def resolve_pptx_skill_root() -> Path | None:
    for root in _candidate_roots():
        if not root.exists():
            continue
        if (root / "SKILL.md").exists():
            return root
    return None


def resolve_pptx_thumbnail_script() -> Path | None:
    for root in _candidate_roots():
        script = root / "scripts" / "thumbnail.py"
        if script.exists():
            return script
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


@lru_cache(maxsize=1)
def load_pptx_skill_docs() -> dict[str, str]:
    for root in _candidate_roots():
        if not root.exists():
            continue
        skill = _read_text(root / "SKILL.md")
        editing = _read_text(root / "editing.md")
        scratch = _read_text(root / "pptxgenjs.md")
        if skill:
            return {
                "root": str(root),
                "skill": skill,
                "editing": editing,
                "scratch": scratch,
            }

    # Hard fallback to bundled template if skill directory is unavailable.
    fallback = _read_text(Path(__file__).with_name("pptx_prompt_template.md"))
    return {
        "root": "fallback",
        "skill": fallback or "PPTX Skill",
        "editing": "",
        "scratch": "",
    }


def build_pptx_skill_context(*, mode: str, template_bound: bool) -> str:
    docs = load_pptx_skill_docs()
    sections: list[str] = []

    sections.append("# PPTX Skill Base\n" + (docs.get("skill") or ""))
    if mode == "revise" or template_bound:
        if docs.get("editing"):
            sections.append("# PPTX Editing Guide\n" + docs["editing"])
    else:
        if docs.get("scratch"):
            sections.append("# PPTX Scratch-Creation Guide\n" + docs["scratch"])

    if mode == "generate" and template_bound and docs.get("scratch"):
        # Always keep scratch guidance available for future no-template modes.
        sections.append("# PPTX Scratch-Creation Reference\n" + docs["scratch"])

    return "\n\n".join(sections).strip()
