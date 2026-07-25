"""
market_lib.py
=============
Shared building blocks for fetching Yahoo Finance data and writing the repo's
output files. Used by:
    fetch_daily.py   -> daily OHLC (^NDX, NQ=F) back to 2019
    fetch_1m.py      -> 1-minute bars (^NDX, NQ=F), accumulated day by day

Design notes
------------
* Yahoo 1m data is only available for the **last ~30 days** and at most **~8
  days per request**, so `download_1m()` fetches in ~7-day chunks and stitches
  them together. History older than 30 days is gone from Yahoo, so 1m coverage
  is built up over time by re-running and appending (see accumulate_1m()).
* All prices are kept at full precision in CSV and rounded to 2dp in JSON.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("market")

# yfinance logs its own noisy errors when a 1m chunk tips past Yahoo's 30-day
# edge; we handle empty chunks ourselves, so keep those out of the CI log.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

SOURCE_NAME = "Yahoo Finance"

DAILY_REQUIRED = ["Date", "Open", "Close"]
DAILY_OUTPUT = ["Date", "Open", "Close", "High", "Low", "Volume", "Adj Close"]
INTRADAY_OUTPUT = ["Datetime", "Open", "High", "Low", "Close", "Volume"]


class DataError(Exception):
    """Raised when downloaded data is missing, empty, or malformed."""


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _flatten_columns(raw: pd.DataFrame) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return raw


# --------------------------------------------------------------------------- #
# Daily
# --------------------------------------------------------------------------- #
def download_daily(ticker: str, start: str) -> pd.DataFrame:
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("Downloading %s DAILY %s..%s", ticker, start, end)
    raw = yf.download(ticker, start=start, interval="1d", auto_adjust=False,
                      actions=False, progress=False, threads=False)
    if raw is None or raw.empty:
        raise DataError(f"No daily data returned for {ticker!r}.")
    raw = _flatten_columns(raw)
    df = raw.reset_index()
    if "Date" not in df.columns:
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Date"})
        elif "index" in df.columns:
            df = df.rename(columns={"index": "Date"})
        else:
            raise DataError(f"No date column. Columns: {list(df.columns)}")
    return df


def shape_daily(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in DAILY_REQUIRED if c not in df.columns]
    if missing:
        raise DataError(f"missing required column(s): {missing}; saw {list(df.columns)}")
    keep = [c for c in DAILY_OUTPUT if c in df.columns]
    df = df[keep].copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["Open", "Close"], how="all")
    df = df.drop_duplicates(subset=["Date"], keep="last")
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def validate_daily(df: pd.DataFrame) -> None:
    if df.empty:
        raise DataError("daily dataframe is empty")
    for c in DAILY_REQUIRED:
        if c not in df.columns:
            raise DataError(f"required column {c!r} missing")
    if df["Date"].duplicated().any():
        raise DataError("duplicate dates")
    if not df["Date"].is_monotonic_increasing:
        raise DataError("dates not sorted ascending")
    for c in ("Open", "Close"):
        if pd.to_numeric(df[c], errors="coerce").notna().sum() == 0:
            raise DataError(f"column {c!r} has no numeric values")
    log.info("Daily validation passed: %d rows, %s .. %s",
             len(df), df["Date"].iloc[0], df["Date"].iloc[-1])


def _daily_records(df: pd.DataFrame) -> list[dict]:
    price_cols = [c for c in ("Open", "Close", "High", "Low", "Adj Close") if c in df.columns]
    out = []
    for _, row in df.iterrows():
        rec: dict = {"Date": str(row["Date"])}
        for c in price_cols:
            rec[c] = _to_float(row[c])
        if "Volume" in df.columns:
            try:
                rec["Volume"] = int(row["Volume"])
            except (TypeError, ValueError):
                rec["Volume"] = None
        out.append(rec)
    return out


def write_daily_outputs(df: pd.DataFrame, outdir: Path, ticker: str,
                        source_url: str, start_date: str, now_utc: str,
                        recent_days: int = 30) -> None:
    """Write history.csv/json, recent_30d.json, latest.json, meta.json."""
    outdir.mkdir(parents=True, exist_ok=True)
    fields = list(df.columns)

    # history.csv (full precision)
    df.to_csv(outdir / "history.csv", index=False, encoding="utf-8")

    # history.json (self-describing, AI-friendly)
    _dump(outdir / "history.json", {
        "ticker": ticker, "source": SOURCE_NAME, "source_url": source_url,
        "start_date": start_date, "last_updated_utc": now_utc,
        "row_count": int(len(df)), "fields": fields,
        "data": _daily_records(df),
    })

    # recent_30d.json
    window = df.tail(recent_days)
    _dump(outdir / f"recent_{recent_days}d.json", {
        "ticker": ticker, "source": SOURCE_NAME, "source_url": source_url,
        "last_updated_utc": now_utc, "row_count": int(len(window)), "fields": fields,
        "window": f"last {recent_days} trading days",
        "date_range": [str(window["Date"].iloc[0]), str(window["Date"].iloc[-1])],
        "data": _daily_records(window),
    })

    # latest.json
    last = df.iloc[-1]
    _dump(outdir / "latest.json", {
        "ticker": ticker, "source": SOURCE_NAME,
        "last_trading_date": str(last["Date"]),
        "open": _to_float(last["Open"]), "close": _to_float(last["Close"]),
        "updated_at_utc": now_utc,
    })

    # meta.json
    _dump(outdir / "meta.json", {
        "ticker": ticker, "source_name": SOURCE_NAME, "source_url": source_url,
        "start_date": start_date, "last_updated_utc": now_utc,
        "row_count": int(len(df)), "fields": fields,
    })
    log.info("Wrote daily outputs -> %s (%d rows)", outdir.relative_to(REPO_ROOT), len(df))


# --------------------------------------------------------------------------- #
# 1-minute (intraday)
# --------------------------------------------------------------------------- #
def download_1m(ticker: str, days: int = 30, chunk: int = 7) -> pd.DataFrame:
    """Fetch up to `days` of 1m bars in <=`chunk`-day windows and stitch them.

    Yahoo allows ~8 days per 1m request and only the last ~30 days total, so we
    walk backwards in overlapping windows and de-duplicate.
    """
    now = datetime.now(timezone.utc)
    frames: list[pd.DataFrame] = []
    d = days
    while d > 0:
        start = (now - timedelta(days=d)).strftime("%Y-%m-%d")
        end = (now - timedelta(days=max(d - chunk - 1, -1))).strftime("%Y-%m-%d")  # +1 day overlap
        try:
            raw = yf.download(ticker, start=start, end=end, interval="1m",
                              auto_adjust=False, progress=False, threads=False)
            if raw is not None and not raw.empty:
                frames.append(_flatten_columns(raw))
        except Exception as exc:  # noqa: BLE001 - one bad chunk shouldn't kill the run
            log.warning("1m chunk %s..%s failed: %s", start, end, exc)
        d -= chunk
    if not frames:
        raise DataError(f"No 1m data returned for {ticker!r} (Yahoo keeps only ~30 days).")
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    log.info("Downloaded %d raw 1m rows for %s", len(df), ticker)
    return df


def shape_1m(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index()
    dtcol = next((c for c in ("Datetime", "Date", "index") if c in df.columns), df.columns[0])
    df = df.rename(columns={dtcol: "Datetime"})
    keep = [c for c in INTRADAY_OUTPUT if c in df.columns]
    if "Open" not in keep or "Close" not in keep:
        raise DataError(f"1m data missing Open/Close; saw {list(df.columns)}")
    df = df[keep].copy()
    df = df.dropna(subset=["Open", "Close"], how="all")
    # Timezone-aware ISO8601 string, e.g. 2026-07-24T09:30:00-04:00 -> stable dedup key
    df["Datetime"] = pd.to_datetime(df["Datetime"]).map(lambda x: x.isoformat())
    df = df.drop_duplicates(subset=["Datetime"], keep="last")
    df = df.sort_values("Datetime").reset_index(drop=True)
    return df


def accumulate_1m(path: Path, new_df: pd.DataFrame) -> pd.DataFrame:
    """Merge freshly downloaded 1m bars into the growing on-disk store."""
    if path.exists():
        old = pd.read_csv(path, dtype={"Datetime": str})
        combined = pd.concat([old, new_df], ignore_index=True)
        added = len(set(new_df["Datetime"]) - set(old["Datetime"]))
    else:
        combined = new_df.copy()
        added = len(new_df)
    combined = combined.drop_duplicates(subset=["Datetime"], keep="last")
    combined = combined.sort_values("Datetime").reset_index(drop=True)
    log.info("Accumulated 1m: +%d new rows -> %d total", added, len(combined))
    return combined


def write_1m_outputs(df: pd.DataFrame, outdir: Path, ticker: str,
                     source_url: str, session: str, now_utc: str) -> None:
    """Write the accumulating history.csv, a latest.json bar, and meta.json.

    No giant history.json here — a years-long 1m file would be huge; the CSV is
    the store and meta.json/latest.json give AI tools a cheap way in.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    df.to_csv(outdir / "history.csv", index=False, encoding="utf-8")

    last = df.iloc[-1]
    _dump(outdir / "latest.json", {
        "ticker": ticker, "source": SOURCE_NAME, "interval": "1m",
        "datetime": str(last["Datetime"]),
        "open": _to_float(last["Open"]), "high": _to_float(last.get("High")),
        "low": _to_float(last.get("Low")), "close": _to_float(last["Close"]),
        "volume": int(last["Volume"]) if "Volume" in df.columns and pd.notna(last["Volume"]) else None,
        "updated_at_utc": now_utc,
    })

    _dump(outdir / "meta.json", {
        "ticker": ticker, "source_name": SOURCE_NAME, "source_url": source_url,
        "interval": "1m", "session": session,
        "last_updated_utc": now_utc, "row_count": int(len(df)),
        "date_range": [str(df["Datetime"].iloc[0]), str(df["Datetime"].iloc[-1])],
        "fields": list(df.columns),
        "note": ("Yahoo only serves the last ~30 days of 1m data; this file is "
                 "accumulated over time by re-running fetch_1m.py, so its history "
                 "grows beyond Yahoo's 30-day window from the first run onward."),
    })
    log.info("Wrote 1m outputs -> %s (%d rows, %s .. %s)", outdir.relative_to(REPO_ROOT),
             len(df), df["Datetime"].iloc[0], df["Datetime"].iloc[-1])


# --------------------------------------------------------------------------- #
def _dump(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
