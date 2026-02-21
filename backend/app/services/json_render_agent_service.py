from __future__ import annotations

import json
import logging
import re
import ast
import textwrap
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DemoAsset, DemoFundamental, DemoPricePoint
from app.providers.factory import get_provider
from app.services.json_render_demo_service import ensure_json_render_demo_seeded, run_json_render_demo_query


logger = logging.getLogger("ppt_agent.json_render_agent")

_FENCE_STRIP_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_SQL_FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|pragma|attach|detach|vacuum|reindex|analyze)\b",
    re.IGNORECASE,
)
_TOOL_CALL_BLOCK_RE = re.compile(r"\[TOOL_CALL\](.*?)\[/TOOL_CALL\]", re.IGNORECASE | re.DOTALL)
_MINIMAX_INVOKE_RE = re.compile(
    r"<invoke\s+name=\"([a-zA-Z0-9_.-]+)\"\s*>(.*?)</invoke>",
    re.IGNORECASE | re.DOTALL,
)
_MINIMAX_PARAM_RE = re.compile(
    r"<parameter\s+name=\"([a-zA-Z0-9_.-]+)\"\s*>(.*?)</parameter>",
    re.IGNORECASE | re.DOTALL,
)

_AGENT_STEP_SYSTEM = (
    "You are an agentic quantitative analyst. "
    "Use the provided tools to gather data, then return a compact dashboard payload. "
    "Return JSON only.\n"
    "Output schema:\n"
    "{\n"
    '  "tool_calls": [{"tool": "tool_name", "args": {...}}],\n'
    '  "final": null\n'
    "}\n"
    "or when ready:\n"
    "{\n"
    '  "tool_calls": [],\n'
    '  "final": {\n'
    '    "intent": "price_trend|sector_compare|fundamentals_table|market_snapshot",\n'
    '    "narrative": "string",\n'
    '    "data_sources": ["demo_assets", "demo_price_points", "demo_fundamentals"],\n'
    '    "state": {\n'
    '      "meta": {"title": "string", "subtitle": "string", "as_of": "YYYY-MM-DD|FY2025"},\n'
    '      "kpis": [{"label": "string", "value": "string", "delta": "string"}],\n'
    '      "chart": {\n'
    '        "type": "line|bar",\n'
    '        "title": "string",\n'
    '        "y_label": "string",\n'
    '        "points": [{"label": "string", "value": 1.23}],\n'
    '        "bars": [{"label": "string", "value": 1.23, "delta": 2.1}]\n'
    "      },\n"
    '      "table": {"title": "string", "columns": ["string"], "rows": [["string"]]},\n'
    '      "narrative": "string",\n'
    '      "followups": ["string"]\n'
    "    }\n"
    "  }\n"
    "}\n"
    "Rules: prefer tool calls first, never invent numbers, and use concise output."
)

_FINAL_SYSTEM = (
    "Produce the final dashboard payload JSON only. "
    "Do not include markdown fences. Use only observed data."
)

_FAST_NARRATIVE_SYSTEM = (
    "You are a quantitative analyst. Rewrite the dashboard narrative in 2-3 concise sentences. "
    "Use only facts present in the provided context and do not invent numbers. "
    "Return plain text only."
)

_LOG_BOX_INNER_WIDTH = 136
_LOG_BODY_MAX_LINES = 8
_ANSI_RESET = "\033[0m"
_COLOR_DEFAULT = "\033[38;5;250m"
_COLOR_LIFECYCLE = "\033[38;5;82m"
_COLOR_LLM = "\033[38;5;39m"
_COLOR_TOOL = "\033[38;5;141m"
_COLOR_FINALIZE = "\033[38;5;220m"
_COLOR_NORMALIZE = "\033[38;5;51m"
_COLOR_WARN = "\033[38;5;214m"
_COLOR_ERROR = "\033[38;5;196m"
_STEP_COLORS = (
    "\033[38;5;45m",
    "\033[38;5;117m",
    "\033[38;5;141m",
    "\033[38;5;214m",
    "\033[38;5;82m",
)

_FINAL_RESPONSE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TOOL_RESPONSE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = Lock()


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _color_for_event(event: str, details: dict[str, Any]) -> str:
    event_lower = str(event or "").lower()
    if any(token in event_lower for token in ("error", "fallback", "rejected")):
        return _COLOR_ERROR
    if "unknown_tool" in event_lower:
        return _COLOR_WARN
    if event_lower.startswith("normalize"):
        return _COLOR_NORMALIZE
    if "finalize" in event_lower:
        return _COLOR_FINALIZE
    if event_lower.startswith("llm_"):
        return _COLOR_LLM
    if event_lower.startswith("tool_"):
        return _COLOR_TOOL

    step_num = _as_int(details.get("step"))
    if step_num is not None and step_num > 0:
        return _STEP_COLORS[(step_num - 1) % len(_STEP_COLORS)]
    if event_lower in {"start", "complete"}:
        return _COLOR_LIFECYCLE
    return _COLOR_DEFAULT


def _build_log_label(event: str, details: dict[str, Any]) -> str:
    trace_id = str(details.get("trace_id") or "").strip()
    step_num = _as_int(details.get("step"))
    parts = [f"JSON-RENDER AGENT :: {event}"]
    if trace_id:
        parts.append(f"trace={trace_id}")
    if step_num is not None:
        parts.append(f"step={step_num}")
    return " | ".join(parts)


def _render_boxed_log(*, label: str, body: str, color: str, full: bool = False) -> str:
    content_width = max(40, int(_LOG_BOX_INNER_WIDTH) - 4)
    wrapped: list[str] = []
    source_lines = str(body or "").splitlines() or [""]
    for source_line in source_lines:
        chunks = textwrap.wrap(
            source_line,
            width=content_width,
            replace_whitespace=False,
            drop_whitespace=False,
        )
        if chunks:
            wrapped.extend(chunks)
        else:
            wrapped.append("")
    if not wrapped:
        wrapped = [""]
    if not full and len(wrapped) > _LOG_BODY_MAX_LINES:
        wrapped = wrapped[: _LOG_BODY_MAX_LINES]
        wrapped[-1] = _preview(wrapped[-1], max(12, content_width - 3)) + "..."

    top = "+" + "-" * _LOG_BOX_INNER_WIDTH + "+"
    header = f"| {_preview(label, content_width).ljust(content_width)} |"
    divider = "| " + "-" * content_width + " |"
    body_lines = [f"| {line.ljust(content_width)} |" for line in wrapped]
    bottom = top
    lines = [top, header, divider, *body_lines, bottom]
    return "\n".join(f"{color}{line}{_ANSI_RESET}" for line in lines)


def _format_log_value(value: Any, *, full: bool = False) -> str:
    if isinstance(value, str):
        return value if full else _preview(value, 220)
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    try:
        if full:
            return json.dumps(value, ensure_ascii=False, indent=2)
        serialized = json.dumps(value, ensure_ascii=False)
    except Exception:
        serialized = repr(value)
    return serialized if full else _preview(serialized, 220)


def _log_agent(event: str, *, force: bool = False, full: bool = False, **details: Any) -> None:
    if not force and not settings.verbose_ai_trace:
        return
    target_logger = logging.getLogger("uvicorn.error")
    if details:
        if full:
            detail_lines: list[str] = [f"json_render_agent_{event}"]
            for key, value in details.items():
                detail_lines.append(f"{key}={_format_log_value(value, full=True)}")
            message = "\n".join(detail_lines)
        else:
            detail_parts: list[str] = []
            for key, value in details.items():
                detail_parts.append(f"{key}={_format_log_value(value, full=False)}")
            message = f"json_render_agent_{event} | {' '.join(detail_parts)}"
    else:
        message = f"json_render_agent_{event}"
    label = _build_log_label(event, details)
    color = _color_for_event(event, details)
    boxed = _render_boxed_log(label=label, body=message, color=color, full=full)

    # FastAPI/Uvicorn installs handlers on uvicorn.error; emitting there keeps
    # trace logs visible in container logs without changing global logging config.
    if target_logger.handlers:
        target_logger.info(boxed)
    else:
        logger.warning(boxed)


def _clone_json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(payload, ensure_ascii=False))
    except Exception:
        return payload


def _normalize_query_for_cache(query: str) -> str:
    return " ".join(str(query or "").lower().split())


def _cache_get(cache: dict[str, tuple[float, dict[str, Any]]], key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        row = cache.get(key)
        if not row:
            return None
        expires_at, value = row
        if expires_at <= now:
            cache.pop(key, None)
            return None
        return _clone_json_payload(value)


def _cache_set(
    cache: dict[str, tuple[float, dict[str, Any]]],
    key: str,
    value: dict[str, Any],
    *,
    ttl_seconds: int,
) -> None:
    ttl = max(1, int(ttl_seconds))
    expires_at = time.monotonic() + ttl
    with _CACHE_LOCK:
        cache[key] = (expires_at, _clone_json_payload(value))


def _generate_text_with_timeout(
    *,
    provider: Any,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    retries: int,
    timeout_seconds: float,
    trace_id: str,
    phase: str,
    step: int | None = None,
) -> str:
    timeout = max(0.1, float(timeout_seconds))
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jr-llm")
    future = executor.submit(
        provider.generate_text,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        retries=retries,
    )
    try:
        return str(future.result(timeout=timeout) or "")
    except FuturesTimeoutError:
        _log_agent(
            "llm_call_timeout",
            force=True,
            trace_id=trace_id,
            phase=phase,
            step=step,
            timeout_sec=round(timeout, 2),
        )
        return ""
    except Exception as exc:
        _log_agent(
            "llm_call_error",
            force=True,
            trace_id=trace_id,
            phase=phase,
            step=step,
            reason=str(exc),
        )
        return ""
    finally:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)


def _detect_confident_intent(query: str) -> str | None:
    lowered = str(query or "").lower()
    if any(token in lowered for token in ("fundamental", "ebit", "cash flow", "revenue", "table")):
        return "fundamentals_table"
    if any(token in lowered for token in ("compare", "comparison", "vs", "versus", "ranking")):
        return "sector_compare"
    if any(token in lowered for token in ("trend", "history", "line", "over time", "timeline", "performance")):
        return "price_trend"
    if any(token in lowered for token in ("snapshot", "overview", "market", "top movers", "watchlist")):
        return "market_snapshot"
    return None


def _summarize_tool_data_for_llm(data: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
            summary[f"{key}_sample"] = value[:2]
        elif isinstance(value, dict):
            summary[f"{key}_keys"] = sorted(list(value.keys()))[:12]
        elif isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
    return summary


def _summarize_observations_for_llm(observations: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    trimmed = observations[-max(1, int(limit)) :]
    out: list[dict[str, Any]] = []
    for row in trimmed:
        if not isinstance(row, dict):
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        out.append(
            {
                "tool": str(row.get("tool", "")),
                "ok": bool(row.get("ok", False)),
                "summary": str(row.get("summary", "")),
                "data_summary": _summarize_tool_data_for_llm(data),
            }
        )
    return out


def _observations_sufficient_for_intent(intent: str | None, observations: list[dict[str, Any]]) -> bool:
    if not intent:
        return False
    for row in reversed(observations):
        if not isinstance(row, dict) or not bool(row.get("ok", False)):
            continue
        tool = str(row.get("tool", "")).strip()
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        if intent == "price_trend" and tool == "get_price_history":
            points = data.get("points") if isinstance(data.get("points"), list) else []
            if len(points) >= 2:
                return True
        if intent == "fundamentals_table" and tool == "get_fundamentals":
            rows = data.get("rows") if isinstance(data.get("rows"), list) else []
            if len(rows) >= 1:
                return True
        if intent in {"sector_compare", "market_snapshot"} and tool in {"get_latest_snapshot", "sql_query"}:
            rows = data.get("rows") if isinstance(data.get("rows"), list) else []
            if len(rows) >= 1:
                return True
        if tool == "sql_query":
            rows = data.get("rows") if isinstance(data.get("rows"), list) else []
            if len(rows) >= 1:
                return True
    return False


def _refine_fast_path_narrative(
    *,
    provider: Any,
    query: str,
    result: dict[str, Any],
    trace_id: str,
) -> None:
    if not settings.json_render_fast_path_refine_narrative:
        return
    if getattr(provider, "name", "mock") == "mock":
        return

    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    context = {
        "query": query,
        "intent": result.get("intent"),
        "current_narrative": result.get("narrative"),
        "meta": state.get("meta"),
        "kpis": (state.get("kpis") or [])[:4],
        "chart": {
            "type": ((state.get("chart") or {}).get("type")),
            "title": ((state.get("chart") or {}).get("title")),
            "points_sample": ((state.get("chart") or {}).get("points") or [])[:4],
            "bars_sample": ((state.get("chart") or {}).get("bars") or [])[:4],
        },
        "table": {
            "title": ((state.get("table") or {}).get("title")),
            "columns": ((state.get("table") or {}).get("columns") or [])[:8],
            "rows_sample": ((state.get("table") or {}).get("rows") or [])[:4],
        },
    }
    context_json = json.dumps(context, ensure_ascii=False)
    _log_agent(
        "fastpath_narrative_request",
        trace_id=trace_id,
        request_chars=len(context_json),
        request_preview=context_json,
    )
    if settings.json_render_full_payload_logs:
        _log_agent(
            "fastpath_narrative_request_full",
            trace_id=trace_id,
            request_json=context,
            full=True,
        )
    try:
        refined = _generate_text_with_timeout(
            provider=provider,
            system_prompt=_FAST_NARRATIVE_SYSTEM,
            user_prompt=context_json,
            max_tokens=220,
            retries=0,
            timeout_seconds=float(settings.json_render_llm_call_timeout_seconds),
            trace_id=trace_id,
            phase="fastpath_narrative",
        ).strip()
    except Exception as exc:
        _log_agent("fastpath_narrative_failed", force=True, trace_id=trace_id, reason=str(exc))
        return
    _log_agent(
        "fastpath_narrative_response",
        trace_id=trace_id,
        output_chars=len(refined),
        output_preview=refined,
    )
    if settings.json_render_full_payload_logs:
        _log_agent(
            "fastpath_narrative_response_full",
            trace_id=trace_id,
            output_text=refined,
            full=True,
        )
    if not refined:
        return
    lowered = refined.lstrip()
    if refined == context_json or lowered.startswith("{") or len(refined) > 600:
        _log_agent(
            "fastpath_narrative_skipped",
            trace_id=trace_id,
            reason="invalid_or_echo_response",
            output_chars=len(refined),
        )
        return
    result["narrative"] = refined
    if isinstance(state, dict):
        state["narrative"] = refined


def _run_fast_path_query(
    db: Session,
    *,
    provider: Any,
    query: str,
    max_points: int,
    trace_id: str,
    refine_narrative: bool = True,
) -> dict[str, Any]:
    result = run_json_render_demo_query(db, query=query, max_points=max_points)
    if refine_narrative:
        _refine_fast_path_narrative(provider=provider, query=query, result=result, trace_id=trace_id)
    _log_agent(
        "fastpath_complete",
        trace_id=trace_id,
        intent=result.get("intent"),
        sources=result.get("data_sources", []),
    )
    return result


def run_agentic_json_render_query(
    db: Session,
    *,
    query: str,
    max_points: int = 12,
    provider_name: str | None = None,
    max_steps: int | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    ensure_json_render_demo_seeded(db)
    provider = get_provider(provider_name)
    trace_id = f"jr-{uuid4().hex[:8]}"
    provider_id = getattr(provider, "name", "unknown")
    cache_key = f"{provider_id}|{max_points}|{_normalize_query_for_cache(query)}"

    if use_cache and settings.json_render_cache_ttl_seconds > 0:
        cached = _cache_get(_FINAL_RESPONSE_CACHE, cache_key)
        if cached:
            _log_agent(
                "cache_hit",
                force=True,
                trace_id=trace_id,
                cache_key=cache_key,
                intent=cached.get("intent"),
            )
            return cached

    _log_agent(
        "start",
        force=True,
        trace_id=trace_id,
        provider=provider_id,
        query=query,
        max_points=max_points,
        max_steps=max_steps,
        use_cache=use_cache,
    )

    confident_intent = _detect_confident_intent(query)
    fastpath_reason: str | None = None
    if settings.json_render_fast_path_enabled:
        if confident_intent:
            fastpath_reason = "confident_intent"
        else:
            requested_steps = int(max_steps) if max_steps is not None else int(settings.json_render_agent_default_max_steps)
            if requested_steps <= 1:
                fastpath_reason = "default_low_latency"

    if fastpath_reason:
        _log_agent(
            "fastpath_selected",
            trace_id=trace_id,
            intent=confident_intent or _detect_intent_from_query(query),
            reason=fastpath_reason,
        )
        fast = _run_fast_path_query(
            db,
            provider=provider,
            query=query,
            max_points=max_points,
            trace_id=trace_id,
        )
        if use_cache and settings.json_render_cache_ttl_seconds > 0:
            _cache_set(
                _FINAL_RESPONSE_CACHE,
                cache_key,
                fast,
                ttl_seconds=settings.json_render_cache_ttl_seconds,
            )
        return fast

    tool_registry = _build_tool_registry(db=db, default_max_points=max_points)
    observations: list[dict[str, Any]] = []
    data_sources_seen: set[str] = set()
    deadline_at = time.monotonic() + max(5.0, float(settings.json_render_agent_deadline_seconds))
    requested_steps = int(max_steps) if max_steps is not None else int(settings.json_render_agent_default_max_steps)
    dynamic_max_steps = max(1, min(requested_steps, 3))
    final_candidate: dict[str, Any] | None = None

    step_num = 1
    while step_num <= dynamic_max_steps:
        if time.monotonic() >= deadline_at:
            _log_agent("deadline_reached", force=True, trace_id=trace_id, step=step_num)
            break
        _log_agent(
            "step_begin",
            trace_id=trace_id,
            step=step_num,
            observation_count=len(observations),
        )
        step_payload = _agent_step(
            provider=provider,
            query=query,
            max_points=max_points,
            tools=tool_registry,
            observations=observations,
            trace_id=trace_id,
            step=step_num,
            deadline_at=deadline_at,
        )
        if not step_payload:
            _log_agent("step_no_payload", force=True, trace_id=trace_id, step=step_num)
            break

        candidate = step_payload.get("final")
        if isinstance(candidate, dict):
            final_candidate = candidate
            _log_agent(
                "step_received_final",
                trace_id=trace_id,
                step=step_num,
                final_keys=list(candidate.keys()),
            )
            break

        tool_calls = step_payload.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            _log_agent("step_no_tool_calls", force=True, trace_id=trace_id, step=step_num)
            break

        executed_any = False
        for call in tool_calls[:4]:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("tool", "")).strip()
            args = call.get("args")
            if not isinstance(args, dict):
                args = {}
            if tool_name not in tool_registry:
                observations.append(
                    {
                        "tool": tool_name,
                        "ok": False,
                        "summary": f"Unknown tool '{tool_name}'",
                        "data": {},
                    }
                )
                _log_agent(
                    "unknown_tool",
                    force=True,
                    trace_id=trace_id,
                    step=step_num,
                    tool=tool_name,
                )
                continue
            executed_any = True
            _log_agent(
                "tool_call",
                trace_id=trace_id,
                step=step_num,
                tool=tool_name,
                args=args,
            )
            result = _run_tool(
                tool_registry=tool_registry,
                tool_name=tool_name,
                args=args,
                trace_id=trace_id,
            )
            for source in result.get("sources", []):
                data_sources_seen.add(str(source))
            observations.append(
                {
                    "tool": tool_name,
                    "ok": bool(result.get("ok", False)),
                    "summary": str(result.get("summary", "")),
                    "data": result.get("data", {}),
                }
            )
            _log_agent(
                "tool_result",
                trace_id=trace_id,
                step=step_num,
                tool=tool_name,
                ok=bool(result.get("ok", False)),
                summary=result.get("summary", ""),
                sources=result.get("sources", []),
                data_keys=sorted(list((result.get("data") or {}).keys())),
            )

        _log_agent(
            "step_complete",
            trace_id=trace_id,
            step=step_num,
            requested_tool_calls=len(tool_calls),
            executed_any=executed_any,
            observation_count=len(observations),
        )
        if not executed_any:
            _log_agent("step_halt_no_execution", force=True, trace_id=trace_id, step=step_num)
            break
        if _observations_sufficient_for_intent(confident_intent, observations):
            _log_agent(
                "step_early_stop",
                trace_id=trace_id,
                step=step_num,
                reason="sufficient_observations",
                intent=confident_intent,
            )
            break
        if step_num >= dynamic_max_steps and dynamic_max_steps < 2 and executed_any:
            dynamic_max_steps = 2
            _log_agent(
                "step_escalated",
                trace_id=trace_id,
                previous_max_steps=1,
                new_max_steps=dynamic_max_steps,
                reason="needs_more_context",
            )
        step_num += 1

    if final_candidate is None:
        if time.monotonic() >= deadline_at:
            _log_agent("finalize_skipped_deadline", force=True, trace_id=trace_id)
        else:
            _log_agent(
                "finalize_begin",
                trace_id=trace_id,
                observation_count=len(observations),
            )
            final_candidate = _agent_finalize(
                provider=provider,
                query=query,
                max_points=max_points,
                observations=observations,
                trace_id=trace_id,
                deadline_at=deadline_at,
            )

    if isinstance(final_candidate, dict):
        normalized = _normalize_final_payload(
            final_candidate,
            query=query,
            fallback_sources=sorted(data_sources_seen),
            trace_id=trace_id,
        )
        if normalized:
            _log_agent(
                "complete",
                force=True,
                trace_id=trace_id,
                provider=provider_id,
                intent=normalized.get("intent"),
                sources=normalized.get("data_sources", []),
            )
            if use_cache and settings.json_render_cache_ttl_seconds > 0:
                _cache_set(
                    _FINAL_RESPONSE_CACHE,
                    cache_key,
                    normalized,
                    ttl_seconds=settings.json_render_cache_ttl_seconds,
                )
            return normalized

    _log_agent(
        "fallback",
        force=True,
        trace_id=trace_id,
        reason="invalid_or_empty_model_output",
        observation_count=len(observations),
    )
    logger.warning("json_render_agent_fallback trace_id=%s reason=invalid_or_empty_model_output", trace_id)
    fallback = _run_fast_path_query(
        db,
        provider=provider,
        query=query,
        max_points=max_points,
        trace_id=trace_id,
        refine_narrative=False,
    )
    if use_cache and settings.json_render_cache_ttl_seconds > 0:
        _cache_set(
            _FINAL_RESPONSE_CACHE,
            cache_key,
            fallback,
            ttl_seconds=settings.json_render_cache_ttl_seconds,
        )
    return fallback


def _agent_step(
    *,
    provider: Any,
    query: str,
    max_points: int,
    tools: dict[str, dict[str, Any]],
    observations: list[dict[str, Any]],
    trace_id: str,
    step: int,
    deadline_at: float | None = None,
) -> dict[str, Any] | None:
    tool_specs = {name: row["description"] for name, row in tools.items()}
    obs_limit = max(1, int(settings.json_render_agent_observation_max_items))
    payload = {
        "query": query,
        "max_points": int(max_points),
        "tools": tool_specs,
        "observations": _summarize_observations_for_llm(observations, limit=obs_limit),
        "instruction": (
            "If more data is needed, return tool_calls only. "
            "If enough data is present, return final payload."
        ),
    }
    request_json = json.dumps(payload, ensure_ascii=False)
    _log_agent(
        "llm_step_request",
        trace_id=trace_id,
        step=step,
        request_chars=len(request_json),
        request_preview=request_json,
    )
    if settings.json_render_full_payload_logs:
        _log_agent(
            "llm_step_request_full",
            trace_id=trace_id,
            step=step,
            request_json=payload,
            full=True,
        )
    timeout_seconds = float(settings.json_render_llm_call_timeout_seconds)
    if deadline_at is not None:
        timeout_seconds = min(timeout_seconds, max(0.1, deadline_at - time.monotonic()))
    raw = _generate_text_with_timeout(
        provider=provider,
        system_prompt=_AGENT_STEP_SYSTEM,
        user_prompt=request_json,
        max_tokens=int(settings.json_render_agent_step_max_tokens),
        retries=0,
        timeout_seconds=timeout_seconds,
        trace_id=trace_id,
        phase="step",
        step=step,
    )
    _log_agent(
        "llm_step_response",
        trace_id=trace_id,
        step=step,
        output_chars=len(raw or ""),
        output_preview=str(raw or ""),
    )
    if settings.json_render_full_payload_logs:
        _log_agent(
            "llm_step_response_full",
            trace_id=trace_id,
            step=step,
            output_text=str(raw or ""),
            full=True,
        )
    parsed = _extract_payload(raw)
    if parsed is None:
        _log_agent("llm_step_parse_failed", force=True, trace_id=trace_id, step=step)
        return None
    if "tool_calls" not in parsed and "final" not in parsed:
        parsed = {"tool_calls": [], "final": parsed}
    if "tool_calls" not in parsed:
        parsed["tool_calls"] = []
    if settings.json_render_full_payload_logs:
        _log_agent(
            "llm_step_parse_payload_full",
            trace_id=trace_id,
            step=step,
            parsed_payload=parsed,
            full=True,
        )
    _log_agent(
        "llm_step_parse_ok",
        trace_id=trace_id,
        step=step,
        has_final=isinstance(parsed.get("final"), dict),
        tool_call_count=len(parsed.get("tool_calls") or []),
    )
    return parsed


def _agent_finalize(
    *,
    provider: Any,
    query: str,
    max_points: int,
    observations: list[dict[str, Any]],
    trace_id: str,
    deadline_at: float | None = None,
) -> dict[str, Any] | None:
    obs_limit = max(1, int(settings.json_render_agent_observation_max_items))
    payload = {
        "query": query,
        "max_points": int(max_points),
        "observations": _summarize_observations_for_llm(observations, limit=obs_limit),
        "required": [
            "intent",
            "narrative",
            "data_sources",
            "state.meta",
            "state.kpis",
            "state.chart",
            "state.table",
            "state.followups",
        ],
    }
    request_json = json.dumps(payload, ensure_ascii=False)
    _log_agent(
        "llm_finalize_request",
        trace_id=trace_id,
        request_chars=len(request_json),
        request_preview=request_json,
    )
    if settings.json_render_full_payload_logs:
        _log_agent(
            "llm_finalize_request_full",
            trace_id=trace_id,
            request_json=payload,
            full=True,
        )
    timeout_seconds = float(settings.json_render_llm_call_timeout_seconds)
    if deadline_at is not None:
        timeout_seconds = min(timeout_seconds, max(0.1, deadline_at - time.monotonic()))
    raw = _generate_text_with_timeout(
        provider=provider,
        system_prompt=_FINAL_SYSTEM,
        user_prompt=request_json,
        max_tokens=int(settings.json_render_agent_finalize_max_tokens),
        retries=0,
        timeout_seconds=timeout_seconds,
        trace_id=trace_id,
        phase="finalize",
    )
    _log_agent(
        "llm_finalize_response",
        trace_id=trace_id,
        output_chars=len(raw or ""),
        output_preview=str(raw or ""),
    )
    if settings.json_render_full_payload_logs:
        _log_agent(
            "llm_finalize_response_full",
            trace_id=trace_id,
            output_text=str(raw or ""),
            full=True,
        )
    parsed = _extract_payload(raw)
    if parsed is None:
        _log_agent("llm_finalize_parse_failed", force=True, trace_id=trace_id)
    else:
        if isinstance(parsed.get("final"), dict):
            parsed = parsed["final"]
        if settings.json_render_full_payload_logs:
            _log_agent(
                "llm_finalize_parse_payload_full",
                trace_id=trace_id,
                parsed_payload=parsed,
                full=True,
            )
        _log_agent(
            "llm_finalize_parse_ok",
            trace_id=trace_id,
            has_state=isinstance(parsed.get("state"), dict),
            keys=list(parsed.keys()),
        )
    return parsed


def _build_tool_registry(*, db: Session, default_max_points: int) -> dict[str, dict[str, Any]]:
    return {
        "list_symbols": {
            "description": "List available symbols with company, sector, and country.",
            "runner": lambda args: _tool_list_symbols(db, limit=int(args.get("limit", 20))),
        },
        "get_price_history": {
            "description": (
                "Get monthly price history for one symbol. "
                "Args: symbol (optional), max_points (optional)."
            ),
            "runner": lambda args: _tool_get_price_history(
                db,
                symbol=args.get("symbol"),
                max_points=int(args.get("max_points", default_max_points)),
            ),
        },
        "get_latest_snapshot": {
            "description": "Get latest close, YTD change, and avg volume for symbols.",
            "runner": lambda args: _tool_get_latest_snapshot(db, symbols=args.get("symbols")),
        },
        "get_fundamentals": {
            "description": "Get revenue, EBIT margin, and free cash flow for symbols and years.",
            "runner": lambda args: _tool_get_fundamentals(
                db,
                symbols=args.get("symbols"),
                years=int(args.get("years", 3)),
            ),
        },
        "sql_query": {
            "description": (
                "Run read-only SQL SELECT on demo tables. "
                "Args: query (required), limit (optional <= 200)."
            ),
            "runner": lambda args: _tool_sql_query(
                db,
                query=str(args.get("query", "")),
                limit=int(args.get("limit", 50)),
            ),
        },
    }


def _run_tool(
    *,
    tool_registry: dict[str, dict[str, Any]],
    tool_name: str,
    args: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    cache_key = ""
    if settings.json_render_tool_cache_ttl_seconds > 0:
        try:
            cache_key = f"{tool_name}|{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        except Exception:
            cache_key = f"{tool_name}|{str(args)}"
        cached = _cache_get(_TOOL_RESPONSE_CACHE, cache_key)
        if cached is not None:
            _log_agent(
                "tool_cache_hit",
                trace_id=trace_id or "",
                tool=tool_name,
                cache_key=cache_key,
            )
            return cached
    try:
        result = tool_registry[tool_name]["runner"](args)
        if (
            cache_key
            and settings.json_render_tool_cache_ttl_seconds > 0
            and isinstance(result, dict)
            and bool(result.get("ok", False))
        ):
            _cache_set(
                _TOOL_RESPONSE_CACHE,
                cache_key,
                result,
                ttl_seconds=settings.json_render_tool_cache_ttl_seconds,
            )
        return result
    except Exception as exc:
        logger.warning("json_render_agent_tool_error tool=%s reason=%s", tool_name, exc)
        return {"ok": False, "summary": f"{tool_name} failed: {exc}", "data": {}, "sources": []}


def _tool_list_symbols(db: Session, *, limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    rows = db.scalars(select(DemoAsset).order_by(DemoAsset.symbol.asc()).limit(limit)).all()
    payload = [
        {
            "symbol": row.symbol,
            "company": row.company,
            "sector": row.sector,
            "country": row.country,
            "currency": row.currency,
        }
        for row in rows
    ]
    return {
        "ok": True,
        "summary": f"Loaded {len(payload)} symbols",
        "data": {"symbols": payload},
        "sources": ["demo_assets"],
    }


def _tool_get_price_history(
    db: Session,
    *,
    symbol: Any = None,
    max_points: int = 12,
) -> dict[str, Any]:
    symbols = db.scalars(select(DemoAsset.symbol).order_by(DemoAsset.symbol.asc())).all()
    available = {str(row).upper() for row in symbols}
    requested = str(symbol or "").strip().upper()
    chosen = requested if requested in available else (sorted(available)[0] if available else "")
    max_points = max(2, min(int(max_points), 60))

    rows = db.scalars(
        select(DemoPricePoint)
        .where(DemoPricePoint.symbol == chosen)
        .order_by(DemoPricePoint.price_date.asc())
    ).all()
    if len(rows) > max_points:
        rows = rows[-max_points:]

    points = [
        {
            "date": row.price_date.isoformat(),
            "month": row.price_date.strftime("%b"),
            "close": round(float(row.close), 4),
            "volume_mn": round(float(row.volume_mn), 4),
        }
        for row in rows
    ]
    return {
        "ok": True,
        "summary": f"Loaded {len(points)} price points for {chosen}",
        "data": {"symbol": chosen, "points": points},
        "sources": ["demo_price_points", "demo_assets"],
    }


def _tool_get_latest_snapshot(db: Session, *, symbols: Any = None) -> dict[str, Any]:
    requested = _normalize_symbol_list(symbols)
    all_symbols = db.scalars(select(DemoAsset.symbol).order_by(DemoAsset.symbol.asc())).all()
    available = [str(row).upper() for row in all_symbols]
    if requested:
        selected = [row for row in available if row in set(requested)]
    else:
        selected = available

    snapshot_rows: list[dict[str, Any]] = []
    for symbol in selected:
        series = db.scalars(
            select(DemoPricePoint)
            .where(DemoPricePoint.symbol == symbol)
            .order_by(DemoPricePoint.price_date.asc())
        ).all()
        if len(series) < 1:
            continue
        first = series[0]
        last = series[-1]
        ytd = 0.0 if first.close == 0 else (float(last.close) - float(first.close)) / float(first.close) * 100.0
        avg_volume = sum(float(row.volume_mn) for row in series) / max(1, len(series))
        snapshot_rows.append(
            {
                "symbol": symbol,
                "as_of": last.price_date.isoformat(),
                "latest_close": round(float(last.close), 4),
                "ytd_pct": round(ytd, 4),
                "avg_volume_mn": round(avg_volume, 4),
            }
        )

    snapshot_rows.sort(key=lambda row: float(row["latest_close"]), reverse=True)
    return {
        "ok": True,
        "summary": f"Loaded snapshot for {len(snapshot_rows)} symbols",
        "data": {"rows": snapshot_rows},
        "sources": ["demo_price_points", "demo_assets"],
    }


def _tool_get_fundamentals(db: Session, *, symbols: Any = None, years: int = 3) -> dict[str, Any]:
    requested = _normalize_symbol_list(symbols)
    years = max(1, min(int(years), 10))

    all_symbols = db.scalars(select(DemoAsset.symbol).order_by(DemoAsset.symbol.asc())).all()
    available = [str(row).upper() for row in all_symbols]
    if requested:
        selected = [row for row in available if row in set(requested)]
    else:
        selected = available

    rows = db.scalars(
        select(DemoFundamental)
        .where(DemoFundamental.symbol.in_(selected))
        .order_by(DemoFundamental.symbol.asc(), DemoFundamental.fiscal_year.desc())
    ).all()
    grouped: dict[str, list[DemoFundamental]] = defaultdict(list)
    for row in rows:
        grouped[row.symbol].append(row)

    out_rows: list[dict[str, Any]] = []
    for symbol in selected:
        for row in grouped.get(symbol, [])[:years]:
            out_rows.append(
                {
                    "symbol": symbol,
                    "fiscal_year": int(row.fiscal_year),
                    "revenue_musd": round(float(row.revenue_musd), 4),
                    "ebit_margin_pct": round(float(row.ebit_margin_pct), 4),
                    "free_cash_flow_musd": round(float(row.free_cash_flow_musd), 4),
                }
            )
    return {
        "ok": True,
        "summary": f"Loaded {len(out_rows)} fundamentals rows",
        "data": {"rows": out_rows},
        "sources": ["demo_fundamentals", "demo_assets"],
    }


def _tool_sql_query(db: Session, *, query: str, limit: int = 50) -> dict[str, Any]:
    query_text = str(query or "").strip()
    if not query_text:
        return {"ok": False, "summary": "Missing SQL query", "data": {}, "sources": []}
    if not query_text.lower().startswith("select"):
        return {"ok": False, "summary": "Only SELECT queries are allowed", "data": {}, "sources": []}
    if ";" in query_text:
        return {"ok": False, "summary": "Semicolons are not allowed", "data": {}, "sources": []}
    if _SQL_FORBIDDEN_RE.search(query_text):
        return {"ok": False, "summary": "Forbidden SQL keyword detected", "data": {}, "sources": []}

    limit = max(1, min(int(limit), 200))
    wrapped = f"SELECT * FROM ({query_text}) AS agent_query LIMIT :limit_rows"
    rows = db.execute(text(wrapped), {"limit_rows": limit}).mappings().all()
    records = [{key: _jsonable(value) for key, value in dict(row).items()} for row in rows]
    columns = list(records[0].keys()) if records else []
    sources = _infer_sources_from_sql(query_text)
    return {
        "ok": True,
        "summary": f"SQL returned {len(records)} row(s)",
        "data": {"columns": columns, "rows": records},
        "sources": sources,
    }


def _normalize_symbol_list(symbols: Any) -> list[str]:
    if symbols is None:
        return []
    if isinstance(symbols, str):
        split = [row.strip().upper() for row in symbols.split(",") if row.strip()]
        return split
    if isinstance(symbols, list):
        out: list[str] = []
        for row in symbols:
            token = str(row or "").strip().upper()
            if token:
                out.append(token)
        return out
    return []


def _infer_sources_from_sql(query: str) -> list[str]:
    lowered = query.lower()
    sources: list[str] = []
    if "demo_assets" in lowered:
        sources.append("demo_assets")
    if "demo_price_points" in lowered:
        sources.append("demo_price_points")
    if "demo_fundamentals" in lowered:
        sources.append("demo_fundamentals")
    return sources or ["demo_assets", "demo_price_points", "demo_fundamentals"]


def _extract_payload(text_block: str) -> dict[str, Any] | None:
    raw = str(text_block or "").strip()
    if not raw:
        return None
    candidates = [raw]
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
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                normalized = _normalize_agent_payload_shape(payload)
                if normalized is not None:
                    return normalized
        except Exception:
            repaired = _repair_json_candidate(candidate)
            try:
                payload = json.loads(repaired)
                if isinstance(payload, dict):
                    normalized = _normalize_agent_payload_shape(payload)
                    if normalized is not None:
                        return normalized
            except Exception:
                continue

    tool_calls: list[dict[str, Any]] = []
    for block in _TOOL_CALL_BLOCK_RE.findall(raw):
        parsed_block = None
        block_text = str(block or "").strip()
        if not block_text:
            continue
        try:
            parsed_block = json.loads(block_text)
        except Exception:
            try:
                parsed_block = json.loads(_repair_json_candidate(block_text))
            except Exception:
                parsed_block = _parse_loose_tool_call_block(block_text)
        if isinstance(parsed_block, dict):
            tool_name = str(parsed_block.get("tool", "")).strip()
            args = parsed_block.get("args")
            if tool_name:
                tool_calls.append(
                    {
                        "tool": tool_name,
                        "args": args if isinstance(args, dict) else {},
                    }
                )
    if tool_calls:
        return {"tool_calls": tool_calls, "final": None}

    for invoke_match in _MINIMAX_INVOKE_RE.finditer(raw):
        tool_name = str(invoke_match.group(1) or "").strip()
        body = str(invoke_match.group(2) or "")
        if not tool_name:
            continue
        args: dict[str, Any] = {}
        for param_name, param_value in _MINIMAX_PARAM_RE.findall(body):
            key = str(param_name or "").strip()
            if not key:
                continue
            value_text = str(param_value or "").strip()
            if not value_text:
                args[key] = ""
                continue
            parsed_value = None
            try:
                parsed_value = json.loads(value_text)
            except Exception:
                cleaned = value_text
                if cleaned.startswith("'") and cleaned.endswith("'"):
                    cleaned = cleaned[1:-1]
                parsed_value = cleaned
            args[key] = parsed_value
        tool_calls.append({"tool": tool_name, "args": args})
    if tool_calls:
        return {"tool_calls": tool_calls, "final": None}
    return None


def _parse_loose_tool_call_block(block_text: str) -> dict[str, Any] | None:
    text_block = str(block_text or "").strip()
    if not text_block:
        return None

    tool_match = re.search(r"tool\s*(?:=>|:)\s*['\"]?([a-zA-Z0-9_.-]+)", text_block, flags=re.IGNORECASE)
    if not tool_match:
        return None
    tool_name = str(tool_match.group(1)).strip()
    if not tool_name:
        return None

    args: dict[str, Any] = {}
    symbols_match = re.search(r"symbols?\s*(?:=>|:)?\s*\[([^\]]+)\]", text_block, flags=re.IGNORECASE)
    if symbols_match:
        raw_symbols = symbols_match.group(1)
        symbols: list[str] = []
        for token in raw_symbols.split(","):
            cleaned = str(token).strip().strip("'\"")
            if cleaned:
                symbols.append(cleaned.upper())
        if symbols:
            args["symbols"] = symbols

    int_fields = ("limit", "years", "max_points")
    for field in int_fields:
        match = re.search(rf"{field}\s*(?:=>|:)?\s*([0-9]+)", text_block, flags=re.IGNORECASE)
        if match:
            try:
                args[field] = int(match.group(1))
            except Exception:
                pass

    query_match = re.search(r"query\s*(?:=>|:)\s*['\"]([^'\"]+)['\"]", text_block, flags=re.IGNORECASE)
    if query_match:
        args["query"] = str(query_match.group(1)).strip()

    return {"tool": tool_name, "args": args}


def _normalize_agent_payload_shape(payload: dict[str, Any]) -> dict[str, Any] | None:
    # Native agent envelope.
    if "tool_calls" in payload or "final" in payload:
        if "tool_calls" not in payload or not isinstance(payload.get("tool_calls"), list):
            payload["tool_calls"] = []
        return payload

    # Some models emit single tool call objects instead of envelope:
    # {"tool":"list_symbols","args":{...}}
    tool_name = str(payload.get("tool", "")).strip()
    if tool_name:
        args = payload.get("args")
        return {
            "tool_calls": [
                {
                    "tool": tool_name,
                    "args": args if isinstance(args, dict) else {},
                }
            ],
            "final": None,
        }

    # Otherwise treat as candidate final payload dict.
    return payload


def _repair_json_candidate(text_block: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for char in str(text_block):
        if escaped:
            out.append(char)
            escaped = False
            continue
        if char == "\\":
            out.append(char)
            escaped = True
            continue
        if char == '"':
            out.append(char)
            in_string = not in_string
            continue
        if in_string and char in ("\r", "\n"):
            out.append("\\n")
            continue
        out.append(char)
    repaired = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", repaired)


def _normalize_final_payload(
    payload: dict[str, Any],
    *,
    query: str,
    fallback_sources: list[str],
    trace_id: str,
) -> dict[str, Any] | None:
    state_input = payload.get("state")
    if not isinstance(state_input, dict):
        state_input = _unflatten_state_payload(payload)
    if not isinstance(state_input, dict):
        _log_agent("normalize_rejected", force=True, trace_id=trace_id, reason="missing_state")
        return None

    narrative = str(payload.get("narrative") or state_input.get("narrative") or "").strip()
    if not narrative:
        _log_agent("normalize_rejected", force=True, trace_id=trace_id, reason="missing_narrative")
        return None

    meta = state_input.get("meta") if isinstance(state_input.get("meta"), dict) else {}
    meta_title = str(meta.get("title") or "Dashboard").strip()
    meta_subtitle = str(meta.get("subtitle") or "Agent-generated analytics").strip()
    meta_as_of = str(meta.get("as_of") or date.today().isoformat()).strip()

    kpis_in = state_input.get("kpis") if isinstance(state_input.get("kpis"), list) else []
    kpis: list[dict[str, str]] = []
    for row in kpis_in[:6]:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        value = str(row.get("value") or "").strip()
        if not label or not value:
            continue
        delta = str(row.get("delta") or "").strip()
        kpis.append({"label": label, "value": value, "delta": delta})

    chart_in = state_input.get("chart") if isinstance(state_input.get("chart"), dict) else {}
    chart_type = str(chart_in.get("type") or "bar").strip().lower()
    chart_type = "line" if chart_type == "line" else "bar"
    chart_title = str(chart_in.get("title") or "Chart").strip()
    chart_y_label = str(chart_in.get("y_label") or "Value").strip()

    points_out: list[dict[str, Any]] = []
    bars_out: list[dict[str, Any]] = []
    if chart_type == "line":
        for row in (chart_in.get("points") or [])[:36]:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            value = _to_number(row.get("value"))
            if not label or value is None:
                continue
            points_out.append({"label": label, "value": value})
        if not points_out:
            chart_type = "bar"
    if chart_type == "bar":
        for row in (chart_in.get("bars") or [])[:36]:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            value = _to_number(row.get("value"))
            if not label or value is None:
                continue
            delta_num = _to_number(row.get("delta"))
            bar_row: dict[str, Any] = {"label": label, "value": value}
            if delta_num is not None:
                bar_row["delta"] = delta_num
            bars_out.append(bar_row)
        if not bars_out:
            inferred = _infer_bars_from_table(table=state_input.get("table"))
            bars_out.extend(inferred)
            if not bars_out:
                _log_agent(
                    "normalize_chart_missing",
                    force=True,
                    trace_id=trace_id,
                    reason="empty_chart_data",
                )

    table_in = state_input.get("table") if isinstance(state_input.get("table"), dict) else {}
    table_title = str(table_in.get("title") or "Table").strip()
    columns_in = table_in.get("columns") if isinstance(table_in.get("columns"), list) else []
    rows_in = table_in.get("rows") if isinstance(table_in.get("rows"), list) else []
    columns: list[str] = []
    column_keys: list[str] = []
    for idx, col in enumerate(columns_in[:12]):
        key, label = _extract_column_descriptor(col, idx=idx)
        columns.append(label)
        column_keys.append(key)

    rows: list[list[str]] = []
    for row in rows_in[:120]:
        if isinstance(row, list):
            rows.append([str(cell) for cell in row[:12]])
        elif isinstance(row, dict):
            if column_keys and any(key and key in row for key in column_keys):
                ordered = [str(row.get(key, "")) if key else "" for key in column_keys[:12]]
            else:
                ordered = [str(val) for val in row.values()]
            rows.append(ordered[:12])
    if not columns:
        if rows:
            columns = [f"Col {idx + 1}" for idx in range(len(rows[0]))]
        else:
            columns = ["Info"]
            rows = [[narrative]]
    if rows:
        non_empty_cell_count = sum(1 for row in rows for cell in row if str(cell or "").strip())
        if non_empty_cell_count == 0 and not kpis and not points_out and not bars_out:
            _log_agent(
                "normalize_rejected",
                force=True,
                trace_id=trace_id,
                reason="empty_table_and_chart",
            )
            return None
    no_data_hint = "no observed data" in narrative.lower()
    if no_data_hint and not kpis and not points_out and not bars_out:
        _log_agent(
            "normalize_rejected",
            force=True,
            trace_id=trace_id,
            reason="narrative_reports_no_data",
        )
        return None
    if not points_out and not bars_out and columns == ["Info"] and len(rows) <= 1 and not kpis:
        _log_agent(
            "normalize_rejected",
            force=True,
            trace_id=trace_id,
            reason="low_signal_payload",
        )
        return None

    followups_in = state_input.get("followups") if isinstance(state_input.get("followups"), list) else []
    followups = [str(row).strip() for row in followups_in if str(row).strip()][:6]
    if not followups:
        followups = [
            "Compare two symbols by latest close and YTD change.",
            "Show monthly trend for one symbol.",
            "Show fundamentals table for selected symbols.",
        ]

    intent = str(payload.get("intent") or "market_snapshot").strip()
    if intent not in {"price_trend", "sector_compare", "fundamentals_table", "market_snapshot"}:
        intent = _detect_intent_from_query(query)

    allowed_sources = {"demo_assets", "demo_price_points", "demo_fundamentals"}
    data_sources_in = payload.get("data_sources")
    data_sources: list[str] = []
    if isinstance(data_sources_in, list):
        for row in data_sources_in:
            token = str(row).strip()
            if token in allowed_sources:
                data_sources.append(token)
    if not data_sources:
        data_sources = [row for row in fallback_sources if row in allowed_sources]
    if not data_sources:
        data_sources = ["demo_assets", "demo_price_points", "demo_fundamentals"]

    state = {
        "meta": {"title": meta_title, "subtitle": meta_subtitle, "as_of": meta_as_of},
        "kpis": kpis,
        "chart": {
            "type": chart_type,
            "title": chart_title,
            "y_label": chart_y_label,
            "points": points_out,
            "bars": bars_out,
        },
        "table": {"title": table_title, "columns": columns, "rows": rows},
        "narrative": narrative,
        "followups": followups,
    }
    _log_agent(
        "normalize_ok",
        trace_id=trace_id,
        intent=intent,
        chart_type=chart_type,
        kpi_count=len(kpis),
        table_rows=len(rows),
        followup_count=len(followups),
    )
    return {
        "query": query,
        "intent": intent,
        "narrative": narrative,
        "data_sources": data_sources,
        "state": state,
        "spec": _build_dashboard_spec(chart_type=chart_type),
        "suggested_followups": followups,
    }


def _unflatten_state_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    dotted_items = {str(k): v for k, v in payload.items() if str(k).startswith("state.")}
    if not dotted_items:
        return None

    state: dict[str, Any] = {}
    for dotted_key, value in dotted_items.items():
        path = dotted_key.split(".")[1:]
        if not path:
            continue
        cursor: dict[str, Any] = state
        for token in path[:-1]:
            next_node = cursor.get(token)
            if not isinstance(next_node, dict):
                next_node = {}
                cursor[token] = next_node
            cursor = next_node
        cursor[path[-1]] = value
    return state


def _build_dashboard_spec(*, chart_type: str) -> dict[str, Any]:
    chart_type = "line" if chart_type == "line" else "bar"
    chart_component = "LineChartCard" if chart_type == "line" else "BarChartCard"
    chart_data_key = "points" if chart_type == "line" else "bars"
    return {
        "root": "dashboard",
        "elements": {
            "dashboard": {
                "type": "DashboardPanel",
                "props": {
                    "title": {"$state": "/meta/title"},
                    "subtitle": {"$state": "/meta/subtitle"},
                    "asOf": {"$state": "/meta/as_of"},
                },
                "children": ["kpis", "chart", "table", "insight", "followups"],
            },
            "kpis": {
                "type": "KpiStrip",
                "props": {"items": {"$state": "/kpis"}},
                "children": [],
            },
            "chart": {
                "type": chart_component,
                "props": {
                    "title": {"$state": "/chart/title"},
                    "yLabel": {"$state": "/chart/y_label"},
                    chart_data_key: {"$state": f"/chart/{chart_data_key}"},
                },
                "children": [],
            },
            "table": {
                "type": "DataTableCard",
                "props": {
                    "title": {"$state": "/table/title"},
                    "columns": {"$state": "/table/columns"},
                    "rows": {"$state": "/table/rows"},
                },
                "children": [],
            },
            "insight": {
                "type": "InsightCard",
                "props": {"title": "Agent summary", "text": {"$state": "/narrative"}},
                "children": [],
            },
            "followups": {
                "type": "FollowupsCard",
                "props": {"items": {"$state": "/followups"}},
                "children": [],
            },
        },
    }


def _detect_intent_from_query(query: str) -> str:
    lowered = str(query or "").lower()
    if any(token in lowered for token in ("fundamental", "ebit", "cash flow", "revenue", "table")):
        return "fundamentals_table"
    if any(token in lowered for token in ("compare", "comparison", "vs", "versus", "ranking")):
        return "sector_compare"
    if any(token in lowered for token in ("trend", "history", "line", "over time", "timeline", "performance")):
        return "price_trend"
    return "market_snapshot"


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text_value = str(value or "").strip()
    if not text_value:
        return None
    cleaned = text_value.replace(",", "")
    try:
        return float(cleaned)
    except Exception:
        return None


def _extract_column_descriptor(column: Any, *, idx: int) -> tuple[str, str]:
    if isinstance(column, dict):
        key = str(column.get("key") or column.get("id") or column.get("field") or "").strip()
        label = str(column.get("label") or column.get("title") or key or f"Col {idx + 1}").strip()
        return key, label or f"Col {idx + 1}"

    raw = str(column or "").strip()
    if not raw:
        return "", f"Col {idx + 1}"

    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                key = str(parsed.get("key") or parsed.get("id") or parsed.get("field") or "").strip()
                label = str(parsed.get("label") or parsed.get("title") or key or raw).strip()
                return key, label
        except Exception:
            pass

    return raw, raw


def _infer_bars_from_table(*, table: Any) -> list[dict[str, Any]]:
    if not isinstance(table, dict):
        return []
    rows = table.get("rows")
    if not isinstance(rows, list):
        return []

    inferred: list[dict[str, Any]] = []
    for raw_row in rows[:24]:
        label = ""
        cells: list[Any] = []

        if isinstance(raw_row, list) and raw_row:
            label = str(raw_row[0]).strip()
            cells = raw_row[1:]
        elif isinstance(raw_row, dict) and raw_row:
            preferred_label = raw_row.get("symbol") or raw_row.get("name") or raw_row.get("label")
            if preferred_label:
                label = str(preferred_label).strip()
            else:
                first_key = next(iter(raw_row.keys()))
                label = str(raw_row.get(first_key, "")).strip()
            cells = [value for _, value in raw_row.items()]
        else:
            continue

        if not label:
            continue
        value: float | None = None
        delta: float | None = None
        for cell in cells:
            numeric = _to_number(str(cell).replace("%", ""))
            if numeric is None:
                continue
            if value is None:
                value = numeric
            elif delta is None:
                delta = numeric
                break
        if value is None:
            continue
        row: dict[str, Any] = {"label": label, "value": value}
        if delta is not None:
            row["delta"] = delta
        inferred.append(row)
    return inferred


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _preview(text_value: str, limit: int) -> str:
    raw = str(text_value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(raw) <= limit:
        return raw
    return raw[:limit].rstrip() + " ..."
