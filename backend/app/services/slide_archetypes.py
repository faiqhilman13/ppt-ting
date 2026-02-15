from __future__ import annotations

from typing import Any

# Slot budgets are intentionally conservative for dense corporate templates.
DEFAULT_SLOT_BUDGETS: dict[str, int] = {
    "TITLE": 90,
    "SUBTITLE": 120,
    "BODY": 420,
    "BULLET": 360,
    "CITATION": 180,
    "TABLE": 280,
    "FOOTER": 90,
    "OTHER": 220,
}

ARCHETYPE_RULES: dict[str, dict[str, Any]] = {
    "executive_summary": {
        "guidance": "Lead with decision-level framing, concise evidence, and explicit business implication.",
        "slot_budgets": {"TITLE": 80, "BODY": 360, "CITATION": 170},
        "example": {
            "TITLE": "AI Ops Transformation: 90-Day Outcomes",
            "BODY": "Automation reduced manual triage workload and improved response speed across priority workflows.",
            "CITATION": "Source: Internal operations report, Q1 2026",
        },
    },
    "agenda": {
        "guidance": "Use structured, scan-friendly sections with parallel phrasing.",
        "slot_budgets": {"TITLE": 80, "BULLET": 320},
        "example": {
            "TITLE": "Agenda",
            "BULLET": "Current state\nStrategy options\nDelivery roadmap\nRisks and mitigations",
        },
    },
    "section_break": {
        "guidance": "Keep language short and directional. This slide transitions the narrative.",
        "slot_budgets": {"TITLE": 70, "SUBTITLE": 100},
        "example": {
            "TITLE": "Execution Roadmap",
            "SUBTITLE": "How we deliver safely and fast",
        },
    },
    "comparison": {
        "guidance": "Contrast alternatives with clear tradeoffs and recommendation bias.",
        "slot_budgets": {"TITLE": 80, "BODY": 340, "BULLET": 320},
        "example": {
            "TITLE": "Build vs Buy for Agent Platform",
            "BODY": "In-house build gives control; managed stack accelerates delivery.",
            "BULLET": "Build: custom control, higher implementation overhead\nBuy: faster rollout, vendor constraints",
        },
    },
    "timeline": {
        "guidance": "Organize milestones chronologically with concrete outcomes.",
        "slot_budgets": {"TITLE": 80, "BODY": 280, "BULLET": 330},
        "example": {
            "TITLE": "90-Day Rollout Timeline",
            "BULLET": "Weeks 1-2: Discovery and baseline\nWeeks 3-6: Pilot and validation\nWeeks 7-12: Scale and governance",
        },
    },
    "kpi": {
        "guidance": "Quantify impact. Use metric-first language and explicit baseline delta.",
        "slot_budgets": {"TITLE": 80, "BODY": 240, "CITATION": 170},
        "example": {
            "TITLE": "Operational KPI Impact",
            "BODY": "Cycle time improved by 28% and exception backlog reduced by 19% after deployment.",
            "CITATION": "Source: Internal KPI dashboard, Jan 2026",
        },
    },
    "table_data": {
        "guidance": "Summarize what the table shows; avoid repeating every cell value in prose.",
        "slot_budgets": {"TITLE": 80, "TABLE": 260, "BODY": 260},
        "example": {
            "TITLE": "Financial Impact Summary",
            "BODY": "Table highlights cost, cycle-time, and throughput improvements by workflow.",
        },
    },
    "quote": {
        "guidance": "Use one short quote and attach attribution/citation.",
        "slot_budgets": {"TITLE": 80, "BODY": 220, "CITATION": 170},
        "example": {
            "TITLE": "Voice of Stakeholder",
            "BODY": '"This cut analyst triage time significantly in the first month."',
            "CITATION": "Source: Program sponsor interview, Feb 2026",
        },
    },
    "closing": {
        "guidance": "End with decision ask, ownership, and next step clarity.",
        "slot_budgets": {"TITLE": 80, "BODY": 320, "BULLET": 280},
        "example": {
            "TITLE": "Decision and Next Steps",
            "BULLET": "Approve phase-2 rollout\nConfirm owners and timeline\nStart governance cadence",
        },
    },
    "general": {
        "guidance": "Use concise executive language with one key message per slide.",
        "slot_budgets": {},
        "example": {
            "TITLE": "Key Insight",
            "BODY": "Summarize the core takeaway and why it matters now.",
        },
    },
}


def classify_slot(slot_name: str) -> str:
    slot = slot_name.upper()
    if "SUBTITLE" in slot:
        return "SUBTITLE"
    if "TITLE" in slot:
        return "TITLE"
    if "BULLET" in slot or "LIST" in slot:
        return "BULLET"
    if "CITATION" in slot or "SOURCE" in slot or "REFERENCE" in slot:
        return "CITATION"
    if "TABLE" in slot:
        return "TABLE"
    if "FOOTER" in slot:
        return "FOOTER"
    if "BODY" in slot or "CONTENT" in slot or "TEXT" in slot:
        return "BODY"
    return "OTHER"


def infer_archetype(slots: list[str]) -> str:
    up = [s.upper() for s in slots]
    joined = " ".join(up)

    if any(key in joined for key in ["AGENDA", "OUTLINE"]):
        return "agenda"
    if any(key in joined for key in ["TIMELINE", "MILESTONE", "PHASE"]):
        return "timeline"
    if any(key in joined for key in ["KPI", "METRIC", "STAT", "IMPACT"]):
        return "kpi"
    if any("TABLE" in s for s in up):
        return "table_data"
    if any("QUOTE" in s for s in up):
        return "quote"
    if any(key in joined for key in ["LEFT", "RIGHT", "PRO", "CON", "VERSUS", "VS"]):
        return "comparison"
    if any(key in joined for key in ["NEXT_STEP", "DECISION", "ASK"]):
        return "closing"

    has_title = any("TITLE" in s for s in up)
    has_subtitle = any("SUBTITLE" in s for s in up)
    has_body = any(classify_slot(s) == "BODY" for s in up)
    has_bullet = any(classify_slot(s) == "BULLET" for s in up)
    has_citation = any(classify_slot(s) == "CITATION" for s in up)

    if has_title and has_subtitle and not has_body and len(slots) <= 3:
        return "section_break"
    if has_citation and (has_body or has_bullet):
        return "executive_summary"
    if has_bullet and has_body:
        return "comparison"

    return "general"


def _dimension_aware_budget(width_inches: float, height_inches: float, font_size_pt: float = 12.0) -> int:
    if width_inches <= 0 or height_inches <= 0:
        return 0

    safe_font = max(8.0, min(float(font_size_pt), 36.0))
    chars_per_inch = (72.0 / safe_font) * 1.8
    lines = height_inches * (72.0 / (safe_font * 1.2))
    budget = int(chars_per_inch * width_inches * lines * 0.7)
    return max(40, budget)


def slot_budget(archetype: str, slot_name: str, slot_context: dict[str, Any] | None = None) -> int:
    slot_type = classify_slot(slot_name)
    arch_cfg = ARCHETYPE_RULES.get(archetype, ARCHETYPE_RULES["general"])
    override = arch_cfg.get("slot_budgets", {}).get(slot_type)
    base_budget = int(override or DEFAULT_SLOT_BUDGETS.get(slot_type, DEFAULT_SLOT_BUDGETS["OTHER"]))

    if slot_context:
        width = float(slot_context.get("width_inches") or 0.0)
        height = float(slot_context.get("height_inches") or 0.0)
        font_size = float(slot_context.get("font_size_pt") or 12.0)
        dynamic_budget = _dimension_aware_budget(width, height, font_size)
        if dynamic_budget > 0:
            return dynamic_budget

    return base_budget


def archetype_guidance(archetype: str) -> str:
    return ARCHETYPE_RULES.get(archetype, ARCHETYPE_RULES["general"]).get("guidance", ARCHETYPE_RULES["general"]["guidance"])


def archetype_examples() -> dict[str, dict[str, str]]:
    return {name: cfg.get("example", {}) for name, cfg in ARCHETYPE_RULES.items()}
