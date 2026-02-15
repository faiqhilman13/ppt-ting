from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import settings


def _source_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _clip(text: str, limit: int) -> str:
    return (text or "")[:limit]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_assets(row: dict[str, Any]) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []

    image = str(row.get("image") or "").strip()
    favicon = str(row.get("favicon") or "").strip()
    if image:
        assets.append({"asset_type": "image", "url": image, "source": "exa.image"})
    if favicon:
        assets.append({"asset_type": "favicon", "url": favicon, "source": "exa.favicon"})

    image_links = row.get("extras", {}).get("imageLinks", []) if isinstance(row.get("extras"), dict) else []
    if isinstance(image_links, list):
        for link in image_links[:6]:
            value = str(link).strip()
            if value:
                assets.append({"asset_type": "image_link", "url": value, "source": "exa.extras.imageLinks"})

    return assets


def _exa_search(query: str, max_results: int) -> list[dict]:
    if not settings.exa_api_key:
        return []

    headers = {
        "x-api-key": settings.exa_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "type": "auto",
        "numResults": max_results,
        "text": True,
    }

    response = requests.post(settings.exa_search_url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    rows = data.get("results", [])

    results: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue

        excerpt = str(row.get("text") or row.get("summary") or "").strip()
        title = str(row.get("title") or "Untitled")
        assets = _normalize_assets(row)

        results.append(
            {
                "source_id": str(row.get("id") or _source_id(url)),
                "title": title,
                "url": url,
                "snippet": _clip(excerpt, 220),
                "excerpt": _clip(excerpt, 1200),
                "retrieved_at": _utc_now(),
                "provider": "exa",
                "score": row.get("score"),
                "published_date": row.get("publishedDate"),
                "author": row.get("author"),
                "asset_metadata": assets,
            }
        )
    return results


def search_web(query: str, max_results: int = 5) -> list[dict]:
    try:
        return _exa_search(query, max_results=max_results)
    except Exception:
        return []


def combine_research(prompt: str, doc_chunks: list[dict], max_web_results: int = 5) -> list[dict]:
    web = search_web(prompt, max_results=max_web_results)
    combined = doc_chunks + web
    return combined
