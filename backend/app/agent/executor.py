from __future__ import annotations

from typing import Any

from app.tools.base import ToolContext
from app.tools.runner import ToolRunner


def execute_plan_step(
    *,
    runner: ToolRunner,
    ctx: ToolContext,
    step: dict[str, Any],
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    tool_name = str(step.get("tool", "")).strip()
    result = runner.run(tool_name=tool_name, tool_input=tool_input, ctx=ctx)
    return {
        "tool": tool_name,
        "ok": result.ok,
        "summary": result.summary,
        "metrics": result.metrics,
        "warnings": result.warnings,
        "error": result.error,
        "payload": result.payload,
    }

