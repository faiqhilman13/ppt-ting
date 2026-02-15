from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.config import settings
from app.services.job_trace import ToolRunRecorder, record_job_event
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import get_tool


class ToolValidationError(ValueError):
    pass


def _type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, Mapping)
    return True


def _validate_schema(input_payload: dict[str, Any], schema: dict[str, Any]) -> None:
    if schema.get("type") == "object" and not isinstance(input_payload, dict):
        raise ToolValidationError("Tool input must be an object")

    required = schema.get("required", []) or []
    for field in required:
        if field not in input_payload:
            raise ToolValidationError(f"Missing required input field '{field}'")

    props = schema.get("properties", {}) or {}
    for key, value in input_payload.items():
        if key not in props:
            if schema.get("additionalProperties", True) is False:
                raise ToolValidationError(f"Unexpected input field '{key}'")
            continue
        prop_type = props[key].get("type")
        if prop_type and not _type_matches(value, prop_type):
            raise ToolValidationError(
                f"Input field '{key}' expected type '{prop_type}', got '{type(value).__name__}'"
            )


class ToolRunner:
    def __init__(self, *, default_timeout: int | None = None):
        self.default_timeout = int(default_timeout or settings.max_tool_runtime_seconds)

    def run(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        tool = get_tool(tool_name)
        if tool is None:
            return ToolResult(ok=False, summary="Tool not found", error=f"Unknown tool: {tool_name}")

        recorder = ToolRunRecorder(job_id=ctx.job_id or "n/a", tool_name=tool_name, input_payload=tool_input)
        try:
            _validate_schema(tool_input, tool.input_schema)
            if ctx.job_id and ctx.job_id != "n/a":
                record_job_event(
                    job_id=ctx.job_id,
                    stage="tool",
                    event_type="tool_start",
                    payload={"tool": tool_name},
                )
            result = tool.run(tool_input, ctx)
            recorder.finish(
                status="ok" if result.ok else "failed",
                output_payload=result.payload,
                artifacts=result.artifacts,
                error=result.error,
            )
            if ctx.job_id and ctx.job_id != "n/a":
                record_job_event(
                    job_id=ctx.job_id,
                    stage="tool",
                    event_type="tool_done",
                    payload={
                        "tool": tool_name,
                        "ok": result.ok,
                        "summary": result.summary,
                        "metrics": result.metrics,
                        "warnings": result.warnings[:5],
                    },
                    severity="warning" if result.warnings else "info",
                )
            return result
        except ToolValidationError as exc:
            recorder.finish(status="failed", error=str(exc))
            return ToolResult(ok=False, summary="Tool input validation failed", error=str(exc))
        except Exception as exc:
            recorder.finish(status="failed", error=str(exc))
            return ToolResult(ok=False, summary="Tool execution failed", error=str(exc))
