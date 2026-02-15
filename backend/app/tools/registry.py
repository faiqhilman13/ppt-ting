from __future__ import annotations

from typing import Iterable

from app.tools.base import Tool

_TOOLS: dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    _TOOLS[tool.name] = tool


def register_many(tools: Iterable[Tool]) -> None:
    for tool in tools:
        register_tool(tool)


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def list_tools() -> list[str]:
    return sorted(_TOOLS.keys())

