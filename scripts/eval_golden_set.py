#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize quality report metrics for PPT Agent decks.")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("backend/storage/app.db"),
        help="Path to sqlite database (default: backend/storage/app.db)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output JSON path.",
    )
    return parser.parse_args()


def _load_rows(db_path: Path) -> list[tuple[str, int, float | None, int, str]]:
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT deck_id, version, score, passes_used, issues_json FROM quality_reports ORDER BY created_at DESC"
        )
        return cur.fetchall()
    finally:
        con.close()


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        print(f"Database not found: {args.db}")
        return 1

    rows = _load_rows(args.db)
    if not rows:
        print("No quality_reports rows found.")
        return 0

    scores = [float(row[2]) for row in rows if row[2] is not None]
    qa_issue_counts: list[int] = []
    warning_counts: list[int] = []
    for _, _, _, _, issues_json in rows:
        try:
            payload = json.loads(issues_json or "{}")
        except Exception:
            payload = {}
        qa_issue_counts.append(len(payload.get("qa_issues", []) or []))
        warning_counts.append(len(payload.get("warnings", []) or []))

    report = {
        "deck_versions": len(rows),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "avg_qa_issues": round(sum(qa_issue_counts) / max(1, len(qa_issue_counts)), 2),
        "avg_warnings": round(sum(warning_counts) / max(1, len(warning_counts)), 2),
    }

    print(json.dumps(report, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote report to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

