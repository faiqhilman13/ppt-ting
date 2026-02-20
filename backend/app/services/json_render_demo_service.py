from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DemoAsset, DemoFundamental, DemoPricePoint


_MONTHLY_DATES = [
    "2025-01-31",
    "2025-02-28",
    "2025-03-31",
    "2025-04-30",
    "2025-05-31",
    "2025-06-30",
    "2025-07-31",
    "2025-08-31",
    "2025-09-30",
    "2025-10-31",
    "2025-11-30",
    "2025-12-31",
]

_ASSET_SEED = [
    {"symbol": "DBS", "company": "DBS Group", "sector": "Banking", "country": "Singapore", "currency": "USD"},
    {"symbol": "BBRI", "company": "Bank Rakyat Indonesia", "sector": "Banking", "country": "Indonesia", "currency": "USD"},
    {"symbol": "PTT", "company": "PTT Public Company", "sector": "Energy", "country": "Thailand", "currency": "USD"},
    {"symbol": "MAYBANK", "company": "Malayan Banking", "sector": "Banking", "country": "Malaysia", "currency": "USD"},
    {"symbol": "VNM", "company": "Vinamilk", "sector": "Consumer Staples", "country": "Vietnam", "currency": "USD"},
]

_PRICE_SEED = {
    "DBS": {
        "close": [28.7, 29.1, 28.9, 30.2, 30.8, 31.6, 31.1, 32.0, 32.4, 33.1, 33.6, 34.2],
        "volume_mn": [6.1, 6.5, 5.8, 7.0, 6.9, 7.4, 6.8, 7.3, 7.1, 7.6, 7.8, 8.0],
    },
    "BBRI": {
        "close": [3.35, 3.44, 3.4, 3.51, 3.63, 3.71, 3.66, 3.74, 3.82, 3.89, 3.95, 4.04],
        "volume_mn": [24.0, 22.8, 25.3, 23.9, 24.8, 26.1, 23.7, 24.9, 25.4, 26.3, 27.1, 27.9],
    },
    "PTT": {
        "close": [0.92, 0.95, 0.93, 0.97, 1.01, 1.03, 1.0, 1.05, 1.08, 1.07, 1.1, 1.14],
        "volume_mn": [38.0, 41.2, 36.4, 39.7, 40.5, 42.1, 38.9, 40.4, 43.3, 41.8, 44.0, 45.6],
    },
    "MAYBANK": {
        "close": [1.96, 1.98, 1.95, 2.02, 2.06, 2.1, 2.08, 2.14, 2.19, 2.23, 2.27, 2.31],
        "volume_mn": [11.5, 11.8, 11.1, 12.4, 12.2, 12.8, 12.0, 12.7, 12.9, 13.1, 13.3, 13.7],
    },
    "VNM": {
        "close": [3.08, 3.12, 3.1, 3.2, 3.24, 3.31, 3.28, 3.36, 3.4, 3.46, 3.52, 3.58],
        "volume_mn": [8.4, 8.8, 8.1, 9.0, 9.2, 9.4, 9.0, 9.5, 9.8, 10.1, 10.3, 10.7],
    },
}

_FUNDAMENTAL_SEED = {
    "DBS": [
        (2023, 13800.0, 41.2, 5100.0),
        (2024, 14450.0, 42.6, 5480.0),
        (2025, 15020.0, 43.4, 5725.0),
    ],
    "BBRI": [
        (2023, 11320.0, 35.8, 4100.0),
        (2024, 11940.0, 36.5, 4380.0),
        (2025, 12510.0, 37.1, 4625.0),
    ],
    "PTT": [
        (2023, 21950.0, 14.8, 2960.0),
        (2024, 22600.0, 15.3, 3175.0),
        (2025, 23240.0, 16.0, 3380.0),
    ],
    "MAYBANK": [
        (2023, 10250.0, 33.9, 3520.0),
        (2024, 10680.0, 34.7, 3715.0),
        (2025, 11130.0, 35.5, 3895.0),
    ],
    "VNM": [
        (2023, 6680.0, 22.5, 1260.0),
        (2024, 6950.0, 23.2, 1380.0),
        (2025, 7260.0, 24.1, 1495.0),
    ],
}


def ensure_json_render_demo_seeded(db: Session) -> None:
    existing = db.scalar(select(func.count()).select_from(DemoAsset)) or 0
    if existing > 0:
        return

    assets = [DemoAsset(**row) for row in _ASSET_SEED]
    db.add_all(assets)

    price_rows: list[DemoPricePoint] = []
    for symbol, seed in _PRICE_SEED.items():
        close = seed["close"]
        volume_mn = seed["volume_mn"]
        for idx, raw_date in enumerate(_MONTHLY_DATES):
            price_rows.append(
                DemoPricePoint(
                    symbol=symbol,
                    price_date=date.fromisoformat(raw_date),
                    close=float(close[idx]),
                    volume_mn=float(volume_mn[idx]),
                )
            )
    db.add_all(price_rows)

    fundamental_rows: list[DemoFundamental] = []
    for symbol, rows in _FUNDAMENTAL_SEED.items():
        for fiscal_year, revenue_musd, ebit_margin_pct, free_cash_flow_musd in rows:
            fundamental_rows.append(
                DemoFundamental(
                    symbol=symbol,
                    fiscal_year=int(fiscal_year),
                    revenue_musd=float(revenue_musd),
                    ebit_margin_pct=float(ebit_margin_pct),
                    free_cash_flow_musd=float(free_cash_flow_musd),
                )
            )
    db.add_all(fundamental_rows)
    db.commit()


def run_json_render_demo_query(db: Session, query: str, max_points: int = 12) -> dict[str, Any]:
    ensure_json_render_demo_seeded(db)

    q = str(query or "").strip()
    assets = db.scalars(select(DemoAsset).order_by(DemoAsset.symbol.asc())).all()
    symbol_map = {row.symbol: row for row in assets}

    intent = _detect_intent(q)
    mentioned_symbols = _extract_symbols(q, assets)

    if intent == "price_trend":
        symbol = mentioned_symbols[0] if mentioned_symbols else "DBS"
        data = _build_trend_payload(db, symbol=symbol, max_points=max_points)
        data["intent"] = intent
        data["query"] = q
        return data

    if intent == "fundamentals_table":
        symbols = mentioned_symbols or [row.symbol for row in assets]
        data = _build_fundamentals_payload(db, symbols=symbols)
        data["intent"] = intent
        data["query"] = q
        return data

    # compare + snapshot share the same shape; compare simply prefers explicit symbols.
    symbols = mentioned_symbols if len(mentioned_symbols) >= 2 else [row.symbol for row in assets]
    data = _build_comparison_payload(db, symbols=symbols, symbol_map=symbol_map, intent=intent)
    data["intent"] = intent
    data["query"] = q
    return data


def _detect_intent(query: str) -> str:
    q = query.lower()
    if any(token in q for token in ("fundamental", "ebit", "cash flow", "revenue", "table")):
        return "fundamentals_table"
    if any(token in q for token in ("compare", "comparison", "vs", "versus", "ranking")):
        return "sector_compare"
    if any(token in q for token in ("trend", "history", "line", "over time", "timeline", "performance")):
        return "price_trend"
    return "market_snapshot"


def _extract_symbols(query: str, assets: list[DemoAsset]) -> list[str]:
    q_upper = query.upper()
    q_lower = query.lower()
    picks: list[str] = []
    for row in assets:
        if row.symbol in q_upper:
            picks.append(row.symbol)
            continue
        if row.company.lower() in q_lower:
            picks.append(row.symbol)
    seen: set[str] = set()
    ordered: list[str] = []
    for symbol in picks:
        if symbol in seen:
            continue
        seen.add(symbol)
        ordered.append(symbol)
    return ordered


def _build_trend_payload(db: Session, *, symbol: str, max_points: int) -> dict[str, Any]:
    rows = db.scalars(
        select(DemoPricePoint).where(DemoPricePoint.symbol == symbol).order_by(DemoPricePoint.price_date.asc())
    ).all()
    if len(rows) > max_points:
        rows = rows[-max_points:]
    if not rows:
        return _empty_payload("No trend data available for the requested symbol.")

    first = rows[0]
    last = rows[-1]
    ytd_pct = _pct_change(first.close, last.close)
    avg_volume = mean([row.volume_mn for row in rows])

    state = {
        "meta": {
            "title": f"{symbol} price trend",
            "subtitle": "Synthetic ASEAN market data in SQLite (demo only)",
            "as_of": last.price_date.isoformat(),
        },
        "kpis": [
            {"label": "Latest close", "value": _fmt_price(last.close), "delta": f"{ytd_pct:+.1f}% YTD"},
            {"label": "Average volume", "value": f"{avg_volume:.1f}M", "delta": "monthly avg"},
            {"label": "Observed months", "value": str(len(rows)), "delta": "2025 sample"},
        ],
        "chart": {
            "type": "line",
            "title": f"{symbol} monthly close",
            "y_label": "Price (USD)",
            "points": [{"label": row.price_date.strftime("%b"), "value": round(row.close, 2)} for row in rows],
        },
        "table": {
            "title": "Recent monthly observations",
            "columns": ["Month", "Close (USD)", "Volume (M)"],
            "rows": [
                [row.price_date.strftime("%b %Y"), f"{row.close:.2f}", f"{row.volume_mn:.1f}"] for row in rows[-6:]
            ],
        },
        "narrative": (
            f"{symbol} closed at {last.close:.2f} USD as of {last.price_date:%b %Y}, "
            f"with a {ytd_pct:+.1f}% move versus the first month in the sample."
        ),
        "followups": [
            "Compare this symbol against another ASEAN peer.",
            "Show a fundamentals table for the same symbol.",
            "Rank all demo symbols by YTD return.",
        ],
    }

    return {
        "narrative": state["narrative"],
        "data_sources": ["demo_assets", "demo_price_points"],
        "state": state,
        "spec": _build_dashboard_spec(chart_type="line"),
        "suggested_followups": state["followups"],
    }


def _build_comparison_payload(
    db: Session,
    *,
    symbols: list[str],
    symbol_map: dict[str, DemoAsset],
    intent: str,
) -> dict[str, Any]:
    rows = db.scalars(
        select(DemoPricePoint)
        .where(DemoPricePoint.symbol.in_(symbols))
        .order_by(DemoPricePoint.symbol.asc(), DemoPricePoint.price_date.asc())
    ).all()
    if not rows:
        return _empty_payload("No comparison data available.")

    grouped: dict[str, list[DemoPricePoint]] = defaultdict(list)
    for row in rows:
        grouped[row.symbol].append(row)

    bars: list[dict[str, Any]] = []
    table_rows: list[list[str]] = []
    for symbol in symbols:
        series = grouped.get(symbol, [])
        if len(series) < 2:
            continue
        first = series[0]
        last = series[-1]
        ytd_pct = _pct_change(first.close, last.close)
        avg_volume = mean([entry.volume_mn for entry in series])
        bars.append({"label": symbol, "value": round(last.close, 2), "delta": round(ytd_pct, 1)})
        table_rows.append(
            [
                symbol,
                symbol_map[symbol].sector,
                f"{last.close:.2f}",
                f"{ytd_pct:+.1f}%",
                f"{avg_volume:.1f}",
            ]
        )

    bars.sort(key=lambda row: row["value"], reverse=True)
    table_rows.sort(key=lambda row: float(row[2]), reverse=True)
    leader = bars[0]["label"] if bars else "N/A"
    leader_change = bars[0]["delta"] if bars else 0.0
    as_of = max((series[-1].price_date for series in grouped.values() if series), default=date.today()).isoformat()

    title = "ASEAN cross-symbol comparison" if intent == "sector_compare" else "ASEAN market snapshot"
    narrative = (
        f"{leader} currently leads the demo basket by price level and posted {leader_change:+.1f}% "
        "YTD change in the synthetic sample."
    )

    state = {
        "meta": {
            "title": title,
            "subtitle": "Synthetic ASEAN market data in SQLite (demo only)",
            "as_of": as_of,
        },
        "kpis": [
            {"label": "Symbols compared", "value": str(len(table_rows)), "delta": "demo universe"},
            {"label": "Top symbol", "value": leader, "delta": f"{leader_change:+.1f}% YTD"},
            {"label": "Average latest close", "value": f"{mean([row['value'] for row in bars]):.2f}", "delta": "USD"},
        ],
        "chart": {
            "type": "bar",
            "title": "Latest close by symbol",
            "y_label": "Price (USD)",
            "bars": bars,
        },
        "table": {
            "title": "Comparison table",
            "columns": ["Symbol", "Sector", "Latest close", "YTD %", "Avg volume (M)"],
            "rows": table_rows,
        },
        "narrative": narrative,
        "followups": [
            "Show a line trend for one symbol.",
            "Filter to banking symbols only.",
            "Show fundamentals for the top two symbols.",
        ],
    }

    return {
        "narrative": narrative,
        "data_sources": ["demo_assets", "demo_price_points"],
        "state": state,
        "spec": _build_dashboard_spec(chart_type="bar"),
        "suggested_followups": state["followups"],
    }


def _build_fundamentals_payload(db: Session, *, symbols: list[str]) -> dict[str, Any]:
    rows = db.scalars(
        select(DemoFundamental)
        .where(DemoFundamental.symbol.in_(symbols))
        .order_by(DemoFundamental.fiscal_year.desc(), DemoFundamental.symbol.asc())
    ).all()
    if not rows:
        return _empty_payload("No fundamentals data available.")

    latest_by_symbol: dict[str, DemoFundamental] = {}
    table_rows: list[list[str]] = []
    for row in rows:
        if row.symbol not in latest_by_symbol:
            latest_by_symbol[row.symbol] = row
        table_rows.append(
            [
                row.symbol,
                str(row.fiscal_year),
                f"{row.revenue_musd:.0f}",
                f"{row.ebit_margin_pct:.1f}%",
                f"{row.free_cash_flow_musd:.0f}",
            ]
        )

    bars = [
        {"label": symbol, "value": round(latest.revenue_musd, 1), "delta": round(latest.ebit_margin_pct, 1)}
        for symbol, latest in latest_by_symbol.items()
    ]
    bars.sort(key=lambda row: row["value"], reverse=True)
    avg_margin = mean([latest.ebit_margin_pct for latest in latest_by_symbol.values()])
    avg_fcf = mean([latest.free_cash_flow_musd for latest in latest_by_symbol.values()])
    top_revenue_symbol = bars[0]["label"] if bars else "N/A"
    top_revenue = bars[0]["value"] if bars else 0.0
    top_margin = bars[0]["delta"] if bars else 0.0

    state = {
        "meta": {
            "title": "Fundamentals table",
            "subtitle": "Synthetic ASEAN fundamentals in SQLite (demo only)",
            "as_of": "FY2025",
        },
        "kpis": [
            {"label": "Symbols covered", "value": str(len(latest_by_symbol)), "delta": "FY2025"},
            {"label": "Top revenue", "value": f"{top_revenue_symbol} ({top_revenue:.0f}M)", "delta": f"margin {top_margin:.1f}%"},
            {"label": "Average free cash flow", "value": f"{avg_fcf:.0f}M", "delta": f"avg margin {avg_margin:.1f}%"},
        ],
        "chart": {
            "type": "bar",
            "title": "FY2025 revenue by symbol",
            "y_label": "Revenue (M USD)",
            "bars": bars,
        },
        "table": {
            "title": "Fundamentals detail",
            "columns": ["Symbol", "FY", "Revenue (M USD)", "EBIT margin", "Free cash flow (M USD)"],
            "rows": table_rows,
        },
        "narrative": (
            f"{top_revenue_symbol} leads FY2025 revenue in this demo dataset. "
            f"Average EBIT margin across the selected symbols is {avg_margin:.1f}%."
        ),
        "followups": [
            "Switch to a monthly price trend for one symbol.",
            "Compare top two symbols by YTD return.",
            "Generate a compact executive snapshot view.",
        ],
    }

    return {
        "narrative": state["narrative"],
        "data_sources": ["demo_assets", "demo_fundamentals"],
        "state": state,
        "spec": _build_dashboard_spec(chart_type="bar"),
        "suggested_followups": state["followups"],
    }


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
                "props": {
                    "items": {"$state": "/kpis"},
                },
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
                "props": {
                    "title": "Agent summary",
                    "text": {"$state": "/narrative"},
                },
                "children": [],
            },
            "followups": {
                "type": "FollowupsCard",
                "props": {
                    "items": {"$state": "/followups"},
                },
                "children": [],
            },
        },
    }


def _empty_payload(message: str) -> dict[str, Any]:
    state = {
        "meta": {"title": "No data", "subtitle": "Demo query service", "as_of": date.today().isoformat()},
        "kpis": [],
        "chart": {"type": "bar", "title": "No chart", "y_label": "Value", "bars": []},
        "table": {"title": "No rows", "columns": ["Info"], "rows": [[message]]},
        "narrative": message,
        "followups": ["Try asking for a trend chart or symbol comparison."],
    }
    return {
        "query": "",
        "intent": "empty",
        "narrative": message,
        "data_sources": ["demo_assets", "demo_price_points", "demo_fundamentals"],
        "state": state,
        "spec": _build_dashboard_spec(chart_type="bar"),
        "suggested_followups": state["followups"],
    }


def _pct_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return (end - start) / start * 100.0


def _fmt_price(value: float) -> str:
    return f"${value:.2f}"

