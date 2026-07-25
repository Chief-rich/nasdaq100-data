"""
build_manifest.py
=================
Scan the dataset folders under data/ and write data/manifest.json — a single
index that lets an AI tool or program discover every dataset in one read:
what it is, where it lives, its raw URL, row count, coverage, and freshness.

Run after fetch_daily.py and fetch_1m.py:
    python src/build_manifest.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

OWNER = "Chief-rich"
REPO = "nasdaq100-data"
RAW_BASE = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/"

# folder -> human context (interval/kind is read from each meta.json where possible)
DATASETS = [
    ("ndx_daily", "^NDX", "Nasdaq-100 index", "1d", "Daily OHLC, 2019-01-01 onward"),
    ("nq_daily", "NQ=F", "E-mini Nasdaq-100 futures (front-month)", "1d", "Daily OHLC, 2019-01-01 onward"),
    ("ndx_1m", "^NDX", "Nasdaq-100 index", "1m", "1-minute bars, US regular session, accumulated"),
    ("nq_1m", "NQ=F", "E-mini Nasdaq-100 futures (front-month)", "1m", "1-minute bars, near-24h, accumulated"),
]


def _date_range(folder: Path, meta: dict) -> list | None:
    if "date_range" in meta:
        return meta["date_range"]
    # daily meta has no date_range — derive from history.csv first/last row
    csv = folder / "history.csv"
    if not csv.exists():
        return None
    import pandas as pd
    df = pd.read_csv(csv)
    col = "Date" if "Date" in df.columns else ("Datetime" if "Datetime" in df.columns else df.columns[0])
    if df.empty:
        return None
    return [str(df[col].iloc[0]), str(df[col].iloc[-1])]


def build() -> int:
    datasets = []
    for folder_name, ticker, instrument, interval, desc in DATASETS:
        folder = DATA_DIR / folder_name
        meta_path = folder / "meta.json"
        if not meta_path.exists():
            print(f"WARN: {meta_path} missing — skipping", file=sys.stderr)
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        files = {p.name: f"data/{folder_name}/{p.name}"
                 for p in sorted(folder.glob("*")) if p.suffix in (".csv", ".json")}
        datasets.append({
            "name": folder_name,
            "ticker": ticker,
            "instrument": instrument,
            "interval": interval,
            "description": desc,
            "path": f"data/{folder_name}/",
            "raw_history_csv": RAW_BASE + f"data/{folder_name}/history.csv",
            "row_count": meta.get("row_count"),
            "date_range": _date_range(folder, meta),
            "last_updated_utc": meta.get("last_updated_utc"),
            "files": files,
        })

    manifest = {
        "repo": REPO,
        "owner": OWNER,
        "description": "Nasdaq-100 market data (index ^NDX and E-mini futures NQ=F), daily and 1-minute, from Yahoo Finance.",
        "source": "Yahoo Finance",
        "raw_base": RAW_BASE,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("Daily data covers 2019-01-01 onward. 1-minute data is limited by "
                 "Yahoo to the last ~30 days and is accumulated over time, so its "
                 "history grows from the first run onward and cannot be backfilled to 2019."),
        "datasets": datasets,
    }
    out = DATA_DIR / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OK -> {out.relative_to(REPO_ROOT)} ({len(datasets)} datasets)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
