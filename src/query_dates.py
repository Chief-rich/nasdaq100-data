"""
query_dates.py
==============
Look up Open / Close for a list of dates from data/history.csv.

If a requested date is not a trading day (weekend / holiday), it falls back to
the most recent PRIOR trading day and reports which date was actually used.

Usage:
    python src/query_dates.py 2020-03-16 2021-01-04 ...
    python src/query_dates.py            # uses the built-in sample of 10 dates
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_CSV = REPO_ROOT / "data" / "history.csv"

# A random spread of 10 dates across different years.
SAMPLE_DATES = [
    "2019-03-15",
    "2019-12-24",
    "2020-06-01",
    "2021-09-20",
    "2022-02-14",
    "2023-03-13",
    "2023-07-10",
    "2024-11-05",
    "2025-04-22",
    "2026-01-05",
]


def lookup(df: pd.DataFrame, requested: str) -> dict:
    """Return Open/Close for `requested`, falling back to the prior trading day."""
    on_or_before = df[df["Date"] <= requested]
    if on_or_before.empty:
        return {"requested_date": requested, "found": False}
    row = on_or_before.iloc[-1]  # df is sorted ascending, so last <= requested
    used = str(row["Date"])
    return {
        "requested_date": requested,
        "used_trading_date": used,
        "is_exact": used == requested,
        "open": round(float(row["Open"]), 2),
        "close": round(float(row["Close"]), 2),
        "found": True,
    }


def main(argv: list[str]) -> int:
    if not HISTORY_CSV.exists():
        print(f"ERROR: {HISTORY_CSV} not found. Run src/fetch_ndx.py first.", file=sys.stderr)
        return 1

    dates = argv[1:] if len(argv) > 1 else SAMPLE_DATES
    df = pd.read_csv(HISTORY_CSV, dtype={"Date": str})
    df = df.sort_values("Date").reset_index(drop=True)

    results = [lookup(df, d) for d in dates]

    # Pretty table
    print(f"\nTicker: ^NDX   Source: Yahoo Finance   (from {HISTORY_CSV.name})\n")
    header = f"{'Requested':<12} {'Trading day':<12} {'Exact?':<7} {'Open':>12} {'Close':>12}"
    print(header)
    print("-" * len(header))
    for r in results:
        if not r["found"]:
            print(f"{r['requested_date']:<12} {'(no data)':<12}")
            continue
        exact = "yes" if r["is_exact"] else "no"
        print(f"{r['requested_date']:<12} {r['used_trading_date']:<12} {exact:<7} "
              f"{r['open']:>12,.2f} {r['close']:>12,.2f}")

    # Also drop a machine-readable copy next to the data.
    out = REPO_ROOT / "data" / "query_result.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSaved JSON -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
