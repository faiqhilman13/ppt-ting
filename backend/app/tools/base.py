from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolContext:
    job_id: str | None = None
    deck_id: str | None = None
    quality_profile: str = "balanced"
    timeout_seconds: int = 45


@dataclass
class ToolResult:
    ok: bool
    summary: str
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float | int | str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "warnings": self.warnings,
            "error": self.error,
            "payload": self.payload,
        }


class Tool(Protocol):
    name: str
    input_schema: dict[str, Any]

    def run(self, tool_input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ...

