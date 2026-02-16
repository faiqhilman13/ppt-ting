from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.providers.factory import get_provider

logger = logging.getLogger("ppt_agent.theme")

PRESET_NAMES = frozenset({
    "default",
    "dark",
    "corporate",
    "midnight_executive",
    "warm_terracotta",
    "teal_trust",
})

THEME_KEYS = [
    "primary",
    "secondary",
    "accent",
    "background",
    "darkBackground",
    "text",
    "textLight",
    "muted",
    "cardFill",
    "cardBorder",
    "headerFont",
    "bodyFont",
]

ALLOWED_FONTS = {
    "Arial",
    "Calibri",
    "Georgia",
    "Cambria",
    "Trebuchet MS",
    "Verdana",
    "Tahoma",
    "Times New Roman",
}

FALLBACK_THEME: dict[str, str] = {
    "primary": "1E2761",
    "secondary": "3949AB",
    "accent": "E8B931",
    "background": "F8FAFC",
    "darkBackground": "1E2761",
    "text": "1E293B",
    "textLight": "F8FAFC",
    "muted": "94A3B8",
    "cardFill": "FFFFFF",
    "cardBorder": "E2E8F0",
    "headerFont": "Georgia",
    "bodyFont": "Calibri",
}

_HEX6_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_FENCE_STRIP_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_SYSTEM_PROMPT = """\
You are a presentation design expert. You will receive either a direct style \
description (e.g. "black and yellow corporate") or a full presentation prompt \
(e.g. "Create a deck about urban farming"). Extract any style/color/theme \
preferences from the text. If none are specified, infer a fitting professional \
palette from the topic.

Return ONLY a JSON object with exactly these 12 keys:
- primary: main brand/heading color (6-char hex, no #)
- secondary: supporting color (6-char hex, no #)
- accent: highlight/call-to-action color (6-char hex, no #)
- background: light slide background (6-char hex, no #)
- darkBackground: dark slide/section background (6-char hex, no #)
- text: primary body text color (6-char hex, no #, must contrast with background)
- textLight: text color for dark backgrounds (6-char hex, no #, must contrast with darkBackground)
- muted: subtle/secondary text color (6-char hex, no #)
- cardFill: card/container background, usually white or near-white (6-char hex, no #)
- cardBorder: card border color (6-char hex, no #)
- headerFont: one of [Arial, Calibri, Georgia, Cambria, Trebuchet MS, Verdana, Tahoma, Times New Roman]
- bodyFont: one of the same list

Rules:
- All colors must be exactly 6 hex characters WITHOUT the # prefix.
- Ensure strong contrast between text and background (WCAG AA minimum).
- Ensure strong contrast between textLight and darkBackground.
- The palette should feel professional and cohesive.
- Return ONLY the JSON object, no markdown fences, no explanation."""


def _heuristic_theme(style_description: str) -> dict[str, str]:
    text = (style_description or "").lower()

    # EY-like branding requests: black + yellow.
    if " ey" in f" {text}" or ("black" in text and "yellow" in text):
        return {
            "primary": "2E2A25",
            "secondary": "4A4742",
            "accent": "FFE600",
            "background": "F7F5EF",
            "darkBackground": "1C1A17",
            "text": "1C1A17",
            "textLight": "FFFDF7",
            "muted": "6F6A62",
            "cardFill": "FFFFFF",
            "cardBorder": "E5E1D7",
            "headerFont": "Georgia",
            "bodyFont": "Calibri",
        }

    if "earth" in text or "sustainable" in text or "energy" in text or "green" in text:
        return {
            "primary": "40695B",
            "secondary": "667C6F",
            "accent": "E3B448",
            "background": "F4F1DE",
            "darkBackground": "2C3E35",
            "text": "2C2C2C",
            "textLight": "FCFCFC",
            "muted": "87A96B",
            "cardFill": "FFFFFF",
            "cardBorder": "DAD7CD",
            "headerFont": "Cambria",
            "bodyFont": "Calibri",
        }

    return dict(FALLBACK_THEME)


def is_preset(theme_input: str) -> bool:
    """Return True if the input matches a known preset theme name."""
    return (theme_input or "").strip().lower().replace(" ", "_") in PRESET_NAMES


def _validate_theme(obj: dict[str, Any]) -> dict[str, str]:
    """Validate and sanitize an LLM-generated theme, filling gaps from FALLBACK_THEME."""
    result: dict[str, str] = {}
    for key in THEME_KEYS:
        value = str(obj.get(key, "")).strip()
        if key in ("headerFont", "bodyFont"):
            result[key] = value if value in ALLOWED_FONTS else FALLBACK_THEME[key]
        else:
            cleaned = value.lstrip("#")
            result[key] = cleaned.upper() if _HEX6_RE.match(cleaned) else FALLBACK_THEME[key]
    return result


def _escape_newlines_in_json_strings(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == '"':
            out.append(ch)
            in_string = not in_string
            continue
        if in_string and ch in ("\r", "\n"):
            if not out or out[-1] != "\\n":
                out.append("\\n")
            continue
        out.append(ch)
    return "".join(out)


def _repair_json_candidate(text: str) -> str:
    repaired = _escape_newlines_in_json_strings(text)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    candidates: list[str] = [raw]
    cleaned = _FENCE_STRIP_RE.sub("", raw).strip()
    if cleaned and cleaned not in candidates:
        candidates.append(cleaned)

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first >= 0 and last > first:
        span = cleaned[first : last + 1].strip()
        if span and span not in candidates:
            candidates.append(span)

    for candidate in candidates:
        for attempt in (candidate, _repair_json_candidate(candidate)):
            try:
                payload = json.loads(attempt)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                continue
    return None


def generate_theme_from_description(
    style_description: str,
    provider_name: str | None = None,
) -> dict[str, str]:
    """Use the LLM to generate a full theme palette from a natural language style description.

    Returns a validated 12-key theme dict.  Falls back to FALLBACK_THEME on any error.
    """
    provider = get_provider(provider_name)
    try:
        raw = provider.generate_text(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=f"Style description: {style_description}",
            max_tokens=1600,
        )
        theme_obj = _extract_json_payload(raw)
        if not theme_obj:
            raise ValueError("Theme response was not valid JSON")
        validated = _validate_theme(theme_obj)
        logger.info(
            "theme_generated description=%s primary=%s accent=%s headerFont=%s",
            style_description[:80],
            validated["primary"],
            validated["accent"],
            validated["headerFont"],
        )
        return validated
    except Exception as exc:
        logger.warning(
            "theme_generation_failed description=%s reason=%s -- using heuristic fallback",
            style_description[:80],
            exc,
        )
        return _heuristic_theme(style_description)
