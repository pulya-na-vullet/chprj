"""Diff two ReviewReportData JSON files by rule_id (T-0042 quality gate).

Usage: uv run python scripts/compare_reviews.py baseline.json candidate.json
"""

import json
import sys
from typing import Any


def load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {r["rule_id"]: r for r in data["risks"]}


def main() -> None:
    base, cand = load(sys.argv[1]), load(sys.argv[2])
    only_base = sorted(set(base) - set(cand))
    only_cand = sorted(set(cand) - set(base))
    changed = [
        (rid, base[rid]["level"], cand[rid]["level"])
        for rid in sorted(set(base) & set(cand))
        if base[rid]["level"] != cand[rid]["level"]
    ]
    print(f"ушли (были в базлайне): {only_base or '—'}")
    print(f"новые (только у кандидата): {only_cand or '—'}")
    print("сменили уровень:", ", ".join(f"{r}: {a}→{b}" for r, a, b in changed) or "—")
    high_lost = [r for r in only_base if base[r]["level"] == "high"]
    if high_lost:
        print(f"FAIL: потеряны high-риски: {high_lost}")
        sys.exit(1)
    print("OK: high-риски базлайна сохранены")


if __name__ == "__main__":
    main()
