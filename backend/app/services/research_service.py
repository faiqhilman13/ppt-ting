from __future__ import annotations

import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS


def _source_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _fetch_excerpt(url: str, limit: int = 500) -> str:
    try:
        response = requests.get(url, timeout=7)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.stripped_strings)
        return text[:limit]
    except Exception:
        return ""


def search_web(query: str, max_results: int = 5) -> list[dict]:
    results: list[dict] = []
    try:
        with DDGS() as ddgs:
            rows = ddgs.text(query, max_results=max_results)
            for row in rows:
                url = row.get("href") or row.get("url")
                if not url:
                    continue
                results.append(
                    {
                        "source_id": _source_id(url),
                        "title": row.get("title") or "Untitled",
                        "url": url,
                        "snippet": row.get("body") or "",
                        "excerpt": _fetch_excerpt(url),
                        "retrieved_at": datetime.utcnow().isoformat(),
                    }
                )
    except Exception:
        pass

    return results


def combine_research(prompt: str, doc_chunks: list[dict], max_web_results: int = 5) -> list[dict]:
    web = search_web(prompt, max_results=max_web_results)
    combined = doc_chunks + web
    return combined
