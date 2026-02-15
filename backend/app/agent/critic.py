from __future__ import annotations

from typing import Any


def collect_qa_issues(*tool_outputs: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for output in tool_outputs:
        payload = output.get("payload") if isinstance(output, dict) else None
        if not isinstance(payload, dict):
            continue
        rows = payload.get("issues")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                issues.append(row)
    return issues


def _issue_penalty(issues: list[dict[str, Any]]) -> tuple[float, int, int]:
    critical_count = 0
    warning_count = 0
    penalty = 0.0
    for issue in issues:
        if str(issue.get("severity", "warning")).lower() == "critical":
            critical_count += 1
            penalty += 10.0
        else:
            warning_count += 1
            penalty += 4.0
    return penalty, critical_count, warning_count


def _warning_penalty(warnings: list[str]) -> tuple[float, dict[str, int]]:
    counts = {
        "trimmed": 0,
        "missing_slot": 0,
        "keyword_alignment": 0,
        "fallback_or_failure": 0,
        "other": 0,
    }
    penalty = 0.0
    for raw in warnings:
        text = str(raw or "").lower()
        if not text:
            continue
        if "trimmed slot" in text:
            counts["trimmed"] += 1
            penalty += 0.45
            continue
        if "filled missing slot" in text or "missing slot" in text:
            counts["missing_slot"] += 1
            penalty += 1.8
            continue
        if "low title/body keyword alignment" in text:
            counts["keyword_alignment"] += 1
            penalty += 1.2
            continue
        if any(token in text for token in ["fallback", "failed", "invalid", "overflow", "error", "unknown"]):
            counts["fallback_or_failure"] += 1
            penalty += 2.8
            continue
        counts["other"] += 1
        penalty += 0.8
    return min(penalty, 35.0), counts


def quality_score_breakdown(
    *,
    issues: list[dict[str, Any]],
    warnings: list[str] | None = None,
    rewrites_applied: int = 0,
    correction_passes_used: int = 0,
) -> dict[str, Any]:
    warnings = [str(row) for row in (warnings or []) if str(row).strip()]
    issue_penalty, critical_issues, warning_issues = _issue_penalty(issues)
    warning_penalty, warning_counts = _warning_penalty(warnings)
    rewrite_penalty = min(max(0, int(rewrites_applied)) * 0.35, 10.0)
    correction_penalty = min(max(0, int(correction_passes_used)) * 1.5, 6.0)

    total_penalty = issue_penalty + warning_penalty + rewrite_penalty + correction_penalty
    score = max(0.0, round(100.0 - total_penalty, 1))
    return {
        "score": score,
        "penalties": {
            "issues": round(issue_penalty, 2),
            "warnings": round(warning_penalty, 2),
            "rewrites": round(rewrite_penalty, 2),
            "correction_passes": round(correction_penalty, 2),
            "total": round(total_penalty, 2),
        },
        "counts": {
            "critical_issues": critical_issues,
            "warning_issues": warning_issues,
            "warnings_total": len(warnings),
            "rewrites_applied": int(rewrites_applied or 0),
            "correction_passes_used": int(correction_passes_used or 0),
            "warning_categories": warning_counts,
        },
    }


def quality_score_from_issues(
    issues: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
    rewrites_applied: int = 0,
    correction_passes_used: int = 0,
) -> float:
    breakdown = quality_score_breakdown(
        issues=issues,
        warnings=warnings,
        rewrites_applied=rewrites_applied,
        correction_passes_used=correction_passes_used,
    )
    return float(breakdown["score"])


def correction_targets_from_issues(issues: list[dict[str, Any]], *, max_slides: int = 6) -> list[int]:
    critical = [issue for issue in issues if str(issue.get("severity", "")).lower() == "critical"]
    pool = critical or issues
    seen: set[int] = set()
    ordered: list[int] = []
    for issue in pool:
        try:
            idx = int(issue.get("slide_index"))
        except Exception:
            continue
        if idx in seen:
            continue
        seen.add(idx)
        ordered.append(idx)
        if len(ordered) >= max_slides:
            break
    return ordered


def should_run_correction_pass(
    *,
    issues: list[dict[str, Any]],
    passes_used: int,
    max_passes: int,
) -> bool:
    if passes_used >= max_passes:
        return False
    return any(str(issue.get("severity", "warning")).lower() == "critical" for issue in issues)
